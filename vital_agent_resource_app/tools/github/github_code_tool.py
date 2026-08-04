import base64
import logging
import time
from typing import Any, Dict, List, Optional

from vital_agent_resource_app.tools.abstract_tool import AbstractTool
from vital_agent_resource_app.tools.tool_request import ToolRequest
from vital_agent_resource_app.tools.tool_response import ToolResponse
from vital_agent_resource_app.tools.github.github_client import (
    GitHubClient, GitHubToolError, rate_limit_remaining
)
from vital_agent_resource_app.tools.github.repo_models import GitHubBranch
from vital_agent_resource_app.tools.github.code_models import (
    GitHubCreateBranchInput, GitHubWriteFileInput, GitHubMergeInput,
    GitHubWriteResult, GitHubMergeResult, GitHubCodeToolOutput
)

logger = logging.getLogger("VitalAgentContainerLogger")


class GitHubCodeTool(AbstractTool):
    """Operations that change repository code.

    Split out from github_repo_tool and github_pr_tool deliberately. Those are
    organised by GitHub resource; this one is organised by authority. Every
    operation here alters code -- a branch ref, a commit, or a merge landing
    commits on a branch -- so "may this agent change code?" is answered by
    whether this tool is registered, rather than by a service-wide config flag
    that cannot distinguish two agents sharing a deployment.

    The config gates still apply underneath as defence in depth:
      create_branch          allow_writes
      create_or_update_file  allow_content_writes        (default off)
      merge_pr               allow_pr_merge              (default off)
    and committing to the default branch additionally needs
    allow_default_branch_writes.
    """

    def __init__(self, config: dict, client: GitHubClient):
        super().__init__(config or {})
        self.client = client
        self._dispatch = {
            GitHubCreateBranchInput: self._create_branch,
            GitHubWriteFileInput: self._write_file,
            GitHubMergeInput: self._merge_pr,
        }

    def get_examples(self) -> List[Dict[str, Any]]:
        """Return list of example requests for the GitHub code tool"""
        return [
            {
                "tool": "github_code_tool",
                "tool_input": {
                    "operation": "create_branch",
                    "owner": "vital-ai",
                    "repo": "vital-ai-sandbox",
                    "branch": "fix/flaky-test"
                }
            },
            {
                "tool": "github_code_tool",
                "tool_input": {
                    "operation": "create_or_update_file",
                    "owner": "vital-ai",
                    "repo": "vital-ai-sandbox",
                    "path": "notes.md",
                    "content": "Investigated the flaky test.\n",
                    "message": "Add investigation notes",
                    "branch": "fix/flaky-test"
                }
            },
            {
                "tool": "github_code_tool",
                "tool_input": {
                    "operation": "merge_pr",
                    "owner": "vital-ai",
                    "repo": "vital-ai-sandbox",
                    "pr_number": 1,
                    "merge_method": "squash"
                }
            }
        ]

    async def handle_tool_request(self, tool_request: ToolRequest) -> ToolResponse:
        start_time = time.time()

        validated_input = tool_request.tool_input
        handler = self._dispatch.get(type(validated_input))

        if handler is None:
            return self._create_error_response(
                f"Unsupported GitHub code tool input type: {type(validated_input).__name__}",
                start_time
            )

        operation = getattr(validated_input, 'operation', 'unknown')
        logger.info(f"GitHub Code Tool - operation={operation}")

        try:
            output = await handler(validated_input)
            self._log_output(output)
            return self._create_success_response(output.model_dump(), start_time)
        except GitHubToolError as e:
            logger.warning(f"GitHub code tool rejected {operation}: {e.message}")
            output = GitHubCodeToolOutput(
                operation=operation,
                repository=self._repo_label(validated_input),
                api_error=e.message,
                api_status_code=e.status_code
            )
            return self._create_success_response(output.model_dump(), start_time)
        except Exception as e:
            logger.error(f"GitHub code tool error during {operation}: {e}")
            return self._create_error_response(str(e), start_time)

    # ------------------------------------------------------------------
    # Operations
    # ------------------------------------------------------------------

    async def _create_branch(self, vi: GitHubCreateBranchInput) -> GitHubCodeToolOutput:
        full_name = self.client.check_repo(vi.owner, vi.repo)
        # A branch is a ref pointing at an existing commit -- no content changes,
        # so this rides on allow_writes rather than allow_content_writes.
        self.client.check_write_allowed('create_branch')

        from_ref = vi.from_ref or await self._default_branch(full_name, vi.owner, vi.repo)

        ref_response = await self.client.call(
            self.client.gh.rest.git.async_get_ref,
            vi.owner, vi.repo, f"heads/{from_ref}",
            context=f"create_branch resolve {full_name}:{from_ref}"
        )
        sha = ((ref_response.json() or {}).get('object') or {}).get('sha')
        if not sha:
            raise GitHubToolError(
                f"Could not resolve '{from_ref}' on {full_name} to a commit."
            )

        response = await self.client.call(
            self.client.gh.rest.git.async_create_ref,
            vi.owner, vi.repo,
            data={'ref': f"refs/heads/{vi.branch}", 'sha': sha},
            context=f"create_branch {full_name}:{vi.branch}"
        )

        created = response.json() or {}
        return GitHubCodeToolOutput(
            operation='create_branch',
            repository=full_name,
            branch=GitHubBranch(
                name=vi.branch,
                sha=(created.get('object') or {}).get('sha') or sha,
                is_default=False,
            ),
            rate_limit_remaining=rate_limit_remaining(response)
        )

    async def _write_file(self, vi: GitHubWriteFileInput) -> GitHubCodeToolOutput:
        full_name = self.client.check_repo(vi.owner, vi.repo)
        self.client.check_write_allowed('create_or_update_file', gate='allow_content_writes')

        default_branch = await self._default_branch(full_name, vi.owner, vi.repo)
        self.client.check_default_branch_write(vi.branch, default_branch, full_name)

        # GitHub needs the current blob SHA to replace an existing file. Look it
        # up rather than making the caller do it, but only when not supplied.
        sha = vi.sha
        if sha is None:
            sha = await self._existing_blob_sha(full_name, vi.owner, vi.repo, vi.path, vi.branch)

        data: Dict[str, Any] = {
            'message': vi.message,
            'content': base64.b64encode(vi.content.encode('utf-8')).decode('ascii'),
            'branch': vi.branch,
        }
        if sha:
            data['sha'] = sha

        response = await self.client.call(
            self.client.gh.rest.repos.async_create_or_update_file_contents,
            vi.owner, vi.repo, vi.path, data=data,
            context=f"create_or_update_file {full_name}:{vi.path} on {vi.branch}"
        )

        raw = response.json() or {}
        commit = raw.get('commit') or {}
        content = raw.get('content') or {}

        return GitHubCodeToolOutput(
            operation='create_or_update_file',
            repository=full_name,
            write_result=GitHubWriteResult(
                path=vi.path,
                branch=vi.branch,
                commit_sha=commit.get('sha'),
                blob_sha=content.get('sha'),
                created=sha is None,
                html_url=commit.get('html_url'),
            ),
            rate_limit_remaining=rate_limit_remaining(response)
        )

    async def _merge_pr(self, vi: GitHubMergeInput) -> GitHubCodeToolOutput:
        full_name = self.client.check_repo(vi.owner, vi.repo)
        self.client.check_write_allowed('merge_pr', gate='allow_pr_merge')

        data: Dict[str, Any] = {'merge_method': vi.merge_method or 'merge'}
        if vi.commit_title:
            data['commit_title'] = vi.commit_title
        if vi.commit_message:
            data['commit_message'] = vi.commit_message
        if vi.sha:
            data['sha'] = vi.sha

        response = await self.client.call(
            self.client.gh.rest.pulls.async_merge,
            vi.owner, vi.repo, vi.pr_number, data=data,
            context=f"merge_pr {full_name}#{vi.pr_number}"
        )

        raw = response.json() or {}
        return GitHubCodeToolOutput(
            operation='merge_pr',
            repository=full_name,
            merge_result=GitHubMergeResult(
                merged=bool(raw.get('merged')),
                sha=raw.get('sha'),
                message=raw.get('message')
            ),
            rate_limit_remaining=rate_limit_remaining(response)
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _default_branch(self, full_name: str, owner: str, repo: str) -> str:
        response = await self.client.call(
            self.client.gh.rest.repos.async_get,
            owner, repo, context=f"resolve default branch {full_name}"
        )
        data = response.json()
        # Defensive: a non-object here would be a GitHub anomaly, and an
        # AttributeError would surface as an opaque tool failure.
        if not isinstance(data, dict):
            raise GitHubToolError(
                f"Unexpected response resolving the default branch for {full_name}."
            )
        return data.get('default_branch') or 'main'

    async def _existing_blob_sha(self, full_name: str, owner: str, repo: str,
                                 path: str, branch: str) -> Optional[str]:
        """Blob SHA of an existing file, or None if it does not exist yet."""
        try:
            response = await self.client.call(
                self.client.gh.rest.repos.async_get_content,
                owner, repo, path, ref=branch,
                context=f"resolve blob sha {full_name}:{path}"
            )
        except GitHubToolError as e:
            if e.status_code == 404:
                return None
            raise
        data = response.json()
        if isinstance(data, list):
            raise GitHubToolError(
                f"'{path}' on {full_name} is a directory, not a file."
            )
        return (data or {}).get('sha')

    @staticmethod
    def _repo_label(validated_input: Any) -> Optional[str]:
        owner = getattr(validated_input, 'owner', None)
        repo = getattr(validated_input, 'repo', None)
        return f"{owner}/{repo}" if owner and repo else None

    @staticmethod
    def _log_output(output: GitHubCodeToolOutput) -> None:
        logger.info("=" * 80)
        logger.info(f"GITHUB CODE TOOL - {output.operation}")
        logger.info("=" * 80)
        logger.info(f"Repository: {output.repository}")
        if output.branch:
            logger.info(f"Created branch {output.branch.name} at {output.branch.sha}")
        if output.write_result:
            w = output.write_result
            logger.info(f"{'Created' if w.created else 'Updated'} {w.path} on {w.branch} "
                        f"-> commit {w.commit_sha}")
        if output.merge_result:
            logger.info(f"Merge: merged={output.merge_result.merged} "
                        f"sha={output.merge_result.sha}")
        logger.info(f"Rate limit remaining: {output.rate_limit_remaining}")
        logger.info("=" * 80)
