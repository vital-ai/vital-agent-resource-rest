import io
import logging
import time
import zipfile
from typing import Any, Dict, List, Optional

from vital_agent_resource_app.tools.abstract_tool import AbstractTool
from vital_agent_resource_app.tools.tool_request import ToolRequest
from vital_agent_resource_app.tools.tool_response import ToolResponse
from vital_agent_resource_app.tools.github.github_client import (
    GitHubClient, GitHubToolError, rate_limit_remaining, has_next_page
)
from vital_agent_resource_app.tools.github.actions_models import (
    GitHubActionsListWorkflowsInput, GitHubActionsListRunsInput,
    GitHubActionsGetRunInput, GitHubActionsListJobsInput,
    GitHubActionsTriggerInput, GitHubActionsCancelRunInput,
    GitHubActionsRerunInput, GitHubActionsRunLogsInput,
    GitHubWorkflow, GitHubWorkflowRun, GitHubWorkflowJob, GitHubWorkflowStep,
    GitHubRunLog, GitHubActionsToolOutput
)

logger = logging.getLogger("VitalAgentContainerLogger")

# Statuses GitHub accepts on the `status` query param that are really conclusions.
_CONCLUSION_VALUES = {'success', 'failure', 'cancelled', 'skipped', 'timed_out', 'action_required'}


class GitHubActionsTool(AbstractTool):
    """GitHub Actions operations.

    Triggering and re-running are gated behind allow_workflow_dispatch (default
    off) because both execute arbitrary CI. Reads ride on no gate; cancelling
    rides on allow_writes.
    """

    def __init__(self, config: dict, client: GitHubClient):
        super().__init__(config or {})
        self.client = client
        self._dispatch = {
            GitHubActionsListWorkflowsInput: self._list_workflows,
            GitHubActionsListRunsInput: self._list_runs,
            GitHubActionsGetRunInput: self._get_run,
            GitHubActionsListJobsInput: self._list_jobs,
            GitHubActionsTriggerInput: self._trigger_workflow,
            GitHubActionsCancelRunInput: self._cancel_run,
            GitHubActionsRerunInput: self._rerun,
            GitHubActionsRunLogsInput: self._get_run_logs,
        }

    def get_examples(self) -> List[Dict[str, Any]]:
        """Return list of example requests for the GitHub actions tool"""
        return [
            {
                "tool": "github_actions_tool",
                "tool_input": {
                    "operation": "list_workflows",
                    "owner": "vital-ai",
                    "repo": "vital-ai-sandbox"
                }
            },
            {
                "tool": "github_actions_tool",
                "tool_input": {
                    "operation": "list_workflow_runs",
                    "owner": "vital-ai",
                    "repo": "vital-ai-sandbox",
                    "branch": "main",
                    "status": "failure",
                    "max_results": 5
                }
            },
            {
                "tool": "github_actions_tool",
                "tool_input": {
                    "operation": "list_run_jobs",
                    "owner": "vital-ai",
                    "repo": "vital-ai-sandbox",
                    "run_id": 123456789
                }
            },
            {
                "tool": "github_actions_tool",
                "tool_input": {
                    "operation": "trigger_workflow",
                    "owner": "vital-ai",
                    "repo": "vital-ai-sandbox",
                    "workflow_id": "ci.yml",
                    "ref": "main"
                }
            }
        ]

    async def handle_tool_request(self, tool_request: ToolRequest) -> ToolResponse:
        start_time = time.time()

        validated_input = tool_request.tool_input
        handler = self._dispatch.get(type(validated_input))

        if handler is None:
            return self._create_error_response(
                f"Unsupported GitHub actions tool input type: {type(validated_input).__name__}",
                start_time
            )

        operation = getattr(validated_input, 'operation', 'unknown')
        logger.info(f"GitHub Actions Tool - operation={operation}")

        try:
            output = await handler(validated_input)
            self._log_output(output)
            return self._create_success_response(output.model_dump(), start_time)
        except GitHubToolError as e:
            logger.warning(f"GitHub actions tool rejected {operation}: {e.message}")
            output = GitHubActionsToolOutput(
                operation=operation,
                repository=self._repo_label(validated_input),
                api_error=e.message,
                api_status_code=e.status_code
            )
            return self._create_success_response(output.model_dump(), start_time)
        except Exception as e:
            logger.error(f"GitHub actions tool error during {operation}: {e}")
            return self._create_error_response(str(e), start_time)

    # ------------------------------------------------------------------
    # Operations
    # ------------------------------------------------------------------

    async def _list_workflows(self, vi: GitHubActionsListWorkflowsInput) -> GitHubActionsToolOutput:
        full_name = self.client.check_repo(vi.owner, vi.repo)
        max_results = vi.max_results or 30

        kwargs: Dict[str, Any] = {'per_page': min(max_results, 100)}
        if vi.page:
            kwargs['page'] = vi.page

        response = await self.client.call(
            self.client.gh.rest.actions.async_list_repo_workflows,
            vi.owner, vi.repo, context=f"list_workflows {full_name}", **kwargs
        )

        raw = response.json() or {}
        workflows = [self._map_workflow(w) for w in raw.get('workflows', [])]

        return GitHubActionsToolOutput(
            operation='list_workflows',
            repository=full_name,
            workflows=workflows[:max_results],
            returned_count=len(workflows[:max_results]),
            total_count=raw.get('total_count'),
            truncated=(raw.get('total_count') or 0) > len(workflows[:max_results]),
            next_page=((vi.page or 1) + 1) if has_next_page(response) else None,
            rate_limit_remaining=rate_limit_remaining(response)
        )

    async def _list_runs(self, vi: GitHubActionsListRunsInput) -> GitHubActionsToolOutput:
        full_name = self.client.check_repo(vi.owner, vi.repo)
        max_results = vi.max_results or 20

        kwargs: Dict[str, Any] = {'per_page': min(max_results, 100)}
        if vi.branch:
            kwargs['branch'] = vi.branch
        if vi.actor:
            kwargs['actor'] = vi.actor
        if vi.event:
            kwargs['event'] = vi.event
        if vi.page:
            kwargs['page'] = vi.page
        if vi.status:
            # GitHub takes both statuses and conclusions on this one param.
            kwargs['status'] = vi.status

        if vi.workflow_id:
            response = await self.client.call(
                self.client.gh.rest.actions.async_list_workflow_runs,
                vi.owner, vi.repo, vi.workflow_id,
                context=f"list_workflow_runs {full_name} workflow={vi.workflow_id}", **kwargs
            )
        else:
            response = await self.client.call(
                self.client.gh.rest.actions.async_list_workflow_runs_for_repo,
                vi.owner, vi.repo,
                context=f"list_workflow_runs {full_name}", **kwargs
            )

        raw = response.json() or {}
        runs = [self._map_run(r) for r in raw.get('workflow_runs', [])]
        returned = runs[:max_results]

        return GitHubActionsToolOutput(
            operation='list_workflow_runs',
            repository=full_name,
            runs=returned,
            returned_count=len(returned),
            total_count=raw.get('total_count'),
            truncated=has_next_page(response) or (raw.get('total_count') or 0) > len(returned),
            next_page=((vi.page or 1) + 1) if has_next_page(response) else None,
            rate_limit_remaining=rate_limit_remaining(response)
        )

    async def _get_run(self, vi: GitHubActionsGetRunInput) -> GitHubActionsToolOutput:
        full_name = self.client.check_repo(vi.owner, vi.repo)
        response = await self.client.call(
            self.client.gh.rest.actions.async_get_workflow_run,
            vi.owner, vi.repo, vi.run_id,
            context=f"get_workflow_run {full_name} run={vi.run_id}"
        )
        return GitHubActionsToolOutput(
            operation='get_workflow_run',
            repository=full_name,
            run=self._map_run(response.json()),
            rate_limit_remaining=rate_limit_remaining(response)
        )

    async def _list_jobs(self, vi: GitHubActionsListJobsInput) -> GitHubActionsToolOutput:
        full_name = self.client.check_repo(vi.owner, vi.repo)
        max_results = vi.max_results or 30

        kwargs: Dict[str, Any] = {
            # githubkit renames the `filter` query param to `filter_` to avoid
            # shadowing the builtin.
            'filter_': vi.filter or 'latest',
            'per_page': min(max_results, 100),
        }
        if vi.page:
            kwargs['page'] = vi.page

        response = await self.client.call(
            self.client.gh.rest.actions.async_list_jobs_for_workflow_run,
            vi.owner, vi.repo, vi.run_id,
            context=f"list_run_jobs {full_name} run={vi.run_id}", **kwargs
        )

        raw = response.json() or {}
        jobs = [self._map_job(j) for j in raw.get('jobs', [])]
        # total_count is the corpus total, so more remain if this page did not
        # reach it -- or if GitHub advertised another page.
        # max_results is the page stride here only because per_page is
        # min(max_results, 100) and max_results is le=100, so the two are always
        # equal. If per_page ever gains its own cap, this offset silently drifts.
        more = has_next_page(response) or \
            (raw.get('total_count') or 0) > (((vi.page or 1) - 1) * max_results
                                             + len(jobs[:max_results]))

        return GitHubActionsToolOutput(
            operation='list_run_jobs',
            repository=full_name,
            jobs=jobs[:max_results],
            returned_count=len(jobs[:max_results]),
            total_count=raw.get('total_count'),
            truncated=more,
            next_page=((vi.page or 1) + 1) if more else None,
            rate_limit_remaining=rate_limit_remaining(response)
        )

    async def _trigger_workflow(self, vi: GitHubActionsTriggerInput) -> GitHubActionsToolOutput:
        full_name = self.client.check_repo(vi.owner, vi.repo)
        self.client.check_write_allowed('trigger_workflow', gate='allow_workflow_dispatch')

        data: Dict[str, Any] = {'ref': vi.ref}
        if vi.inputs:
            data['inputs'] = vi.inputs

        response = await self.client.call(
            self.client.gh.rest.actions.async_create_workflow_dispatch,
            vi.owner, vi.repo, vi.workflow_id, data=data,
            context=f"trigger_workflow {full_name} workflow={vi.workflow_id} ref={vi.ref}"
        )

        # The dispatch endpoint returns 204 with no body -- there is no run id to
        # report. Look for the newest matching run so the caller gets something
        # actionable, but say plainly that the match is best-effort.
        note = ("workflow_dispatch returns no run id. The run below, if any, is the newest "
                "run of this workflow on this ref and is a best-effort match; a run started "
                "by someone else moments earlier could match instead.")
        newest = None
        try:
            lookup = await self.client.call(
                self.client.gh.rest.actions.async_list_workflow_runs,
                vi.owner, vi.repo, vi.workflow_id, branch=vi.ref, per_page=1,
                context=f"trigger_workflow lookup {full_name}"
            )
            runs = (lookup.json() or {}).get('workflow_runs', [])
            newest = self._map_run(runs[0]) if runs else None
            if newest is None:
                note += " No run was visible yet; GitHub may not have created it."
        except GitHubToolError as e:
            note += f" Run lookup failed: {e.message}"

        return GitHubActionsToolOutput(
            operation='trigger_workflow',
            repository=full_name,
            triggered=True,
            run=newest,
            dispatch_note=note,
            rate_limit_remaining=rate_limit_remaining(response)
        )

    async def _cancel_run(self, vi: GitHubActionsCancelRunInput) -> GitHubActionsToolOutput:
        full_name = self.client.check_repo(vi.owner, vi.repo)
        self.client.check_write_allowed('cancel_workflow_run')

        response = await self.client.call(
            self.client.gh.rest.actions.async_cancel_workflow_run,
            vi.owner, vi.repo, vi.run_id,
            context=f"cancel_workflow_run {full_name} run={vi.run_id}"
        )
        return GitHubActionsToolOutput(
            operation='cancel_workflow_run',
            repository=full_name,
            rate_limit_remaining=rate_limit_remaining(response)
        )

    async def _rerun(self, vi: GitHubActionsRerunInput) -> GitHubActionsToolOutput:
        full_name = self.client.check_repo(vi.owner, vi.repo)
        # A re-run executes CI exactly as a fresh dispatch does.
        self.client.check_write_allowed('rerun_workflow', gate='allow_workflow_dispatch')

        func = (self.client.gh.rest.actions.async_re_run_workflow_failed_jobs
                if vi.failed_jobs_only
                else self.client.gh.rest.actions.async_re_run_workflow)

        response = await self.client.call(
            func, vi.owner, vi.repo, vi.run_id,
            context=f"rerun_workflow {full_name} run={vi.run_id}"
        )
        return GitHubActionsToolOutput(
            operation='rerun_workflow',
            repository=full_name,
            triggered=True,
            rate_limit_remaining=rate_limit_remaining(response)
        )

    async def _get_run_logs(self, vi: GitHubActionsRunLogsInput) -> GitHubActionsToolOutput:
        full_name = self.client.check_repo(vi.owner, vi.repo)

        response = await self.client.call(
            self.client.gh.rest.actions.async_download_workflow_run_logs,
            vi.owner, vi.repo, vi.run_id,
            context=f"get_run_logs {full_name} run={vi.run_id}"
        )

        logs = self._extract_logs(
            response.content,
            max_files=vi.max_files or 10,
            max_lines=vi.max_lines_per_file or 50
        )

        return GitHubActionsToolOutput(
            operation='get_run_logs',
            repository=full_name,
            logs=logs,
            returned_count=len(logs),
            truncated=any(log.truncated for log in logs),
            rate_limit_remaining=rate_limit_remaining(response)
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_logs(content: bytes, max_files: int, max_lines: int) -> List[GitHubRunLog]:
        """Unpack the log zip and keep only the tail of each file.

        Raw CI logs run to megabytes; returning them whole would swamp an
        agent's context and is never what the caller wants.
        """
        if not content:
            return []

        try:
            archive = zipfile.ZipFile(io.BytesIO(content))
        except zipfile.BadZipFile:
            # Not a zip -- treat whatever came back as plain text.
            text = content.decode('utf-8', errors='replace')
            lines = text.splitlines()
            return [GitHubRunLog(
                filename='(raw)',
                lines=lines[-max_lines:],
                truncated=len(lines) > max_lines
            )]

        logs = []
        # Top-level entries are per-job summaries; prefer those over the
        # per-step files nested in directories.
        names = [n for n in archive.namelist() if n.endswith('.txt') and '/' not in n]
        if not names:
            names = [n for n in archive.namelist() if n.endswith('.txt')]

        for name in sorted(names)[:max_files]:
            try:
                raw = archive.read(name).decode('utf-8', errors='replace')
            except Exception as e:
                logger.warning(f"Could not read {name} from log archive: {e}")
                continue
            lines = raw.splitlines()
            logs.append(GitHubRunLog(
                filename=name,
                lines=lines[-max_lines:],
                truncated=len(lines) > max_lines
            ))

        return logs

    @staticmethod
    def _repo_label(validated_input: Any) -> Optional[str]:
        owner = getattr(validated_input, 'owner', None)
        repo = getattr(validated_input, 'repo', None)
        return f"{owner}/{repo}" if owner and repo else None

    @staticmethod
    def _map_workflow(data: dict) -> GitHubWorkflow:
        return GitHubWorkflow(
            id=data.get('id'),
            name=data.get('name') or '',
            path=data.get('path'),
            state=data.get('state'),
            html_url=data.get('html_url'),
            created_at=data.get('created_at'),
            updated_at=data.get('updated_at')
        )

    @staticmethod
    def _map_run(data: Optional[dict]) -> Optional[GitHubWorkflowRun]:
        if not data:
            return None
        actor = data.get('actor') or data.get('triggering_actor') or {}
        return GitHubWorkflowRun(
            id=data.get('id'),
            name=data.get('name'),
            run_number=data.get('run_number'),
            status=data.get('status'),
            conclusion=data.get('conclusion'),
            event=data.get('event'),
            branch=data.get('head_branch'),
            head_sha=data.get('head_sha'),
            actor=actor.get('login') if isinstance(actor, dict) else None,
            html_url=data.get('html_url'),
            run_attempt=data.get('run_attempt'),
            created_at=data.get('created_at'),
            updated_at=data.get('updated_at')
        )

    @staticmethod
    def _map_job(data: dict) -> GitHubWorkflowJob:
        return GitHubWorkflowJob(
            id=data.get('id'),
            name=data.get('name') or '',
            status=data.get('status'),
            conclusion=data.get('conclusion'),
            html_url=data.get('html_url'),
            started_at=data.get('started_at'),
            completed_at=data.get('completed_at'),
            steps=[GitHubWorkflowStep(
                name=s.get('name') or '',
                status=s.get('status'),
                conclusion=s.get('conclusion'),
                number=s.get('number')
            ) for s in (data.get('steps') or [])]
        )

    @staticmethod
    def _log_output(output: GitHubActionsToolOutput) -> None:
        logger.info("=" * 80)
        logger.info(f"GITHUB ACTIONS TOOL - {output.operation}")
        logger.info("=" * 80)
        logger.info(f"Repository: {output.repository}")

        if output.workflows:
            logger.info(f"Workflows: {len(output.workflows)}")
            for wf in output.workflows:
                logger.info(f"  [{wf.state}] {wf.name} ({wf.path})")

        if output.runs:
            logger.info(f"Runs: {len(output.runs)} (truncated={output.truncated})")
            for run in output.runs:
                logger.info(f"  #{run.run_number} {run.name} [{run.status}/{run.conclusion}] "
                            f"{run.branch} by {run.actor}")

        if output.run:
            run = output.run
            logger.info(f"Run {run.id}: {run.name} [{run.status}/{run.conclusion}] on {run.branch}")

        if output.jobs:
            logger.info(f"Jobs: {len(output.jobs)}")
            for job in output.jobs:
                logger.info(f"  {job.name} [{job.status}/{job.conclusion}] "
                            f"{len(job.steps)} steps")

        if output.logs:
            logger.info(f"Log files: {[log.filename for log in output.logs]}")

        if output.triggered:
            logger.info(f"Triggered: {output.triggered}")
            if output.dispatch_note:
                logger.info(f"  Note: {output.dispatch_note}")

        logger.info(f"Rate limit remaining: {output.rate_limit_remaining}")
        logger.info("=" * 80)
