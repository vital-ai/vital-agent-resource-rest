import base64
import binascii
import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from vital_agent_resource_app.tools.abstract_tool import AbstractTool
from vital_agent_resource_app.tools.tool_request import ToolRequest
from vital_agent_resource_app.tools.tool_response import ToolResponse
from vital_agent_resource_app.tools.github.github_client import (
    GitHubClient, GitHubToolError, rate_limit_remaining, has_next_page
)
from vital_agent_resource_app.tools.github.repo_models import (
    GitHubRepoGetInput, GitHubGetFileInput, GitHubListBranchesInput,
    GitHubListCommitsInput, GitHubCompareRefsInput, GitHubGetCommitInput,
    GitHubRepository, GitHubFileContent, GitHubBranch, GitHubCommit,
    GitHubComparison, GitHubRepoToolOutput
)

logger = logging.getLogger("VitalAgentContainerLogger")

# Diff hunks are unbounded; same cap the PR tool uses.
MAX_PATCH_CHARS = 2000


class GitHubRepoTool(AbstractTool):
    """Repository metadata, contents and refs -- reads only.

    Every operation here is a read, gated only by the repo allowlist, so
    registering this tool grants an agent no ability to change anything.
    Operations that alter code (create_branch, create_or_update_file) live in
    github_code_tool: authority, not GitHub resource, decides the boundary.
    """

    def __init__(self, config: dict, client: GitHubClient):
        super().__init__(config or {})
        self.client = client
        self._dispatch = {
            GitHubRepoGetInput: self._get_repo,
            GitHubGetFileInput: self._get_file_contents,
            GitHubListBranchesInput: self._list_branches,
            GitHubListCommitsInput: self._list_commits,
            GitHubCompareRefsInput: self._compare_refs,
            GitHubGetCommitInput: self._get_commit,
        }

    def get_examples(self) -> List[Dict[str, Any]]:
        """Return list of example requests for the GitHub repository tool"""
        return [
            {
                "tool": "github_repo_tool",
                "tool_input": {
                    "operation": "get_repo",
                    "owner": "vital-ai",
                    "repo": "vital-ai-sandbox"
                }
            },
            {
                "tool": "github_repo_tool",
                "tool_input": {
                    "operation": "get_file_contents",
                    "owner": "vital-ai",
                    "repo": "vital-ai-sandbox",
                    "path": "README.md"
                }
            },
            {
                "tool": "github_repo_tool",
                "tool_input": {
                    "operation": "compare_refs",
                    "owner": "vital-ai",
                    "repo": "vital-ai-sandbox",
                    "base": "main",
                    "head": "fix/flaky-test"
                }
            }
        ]

    async def handle_tool_request(self, tool_request: ToolRequest) -> ToolResponse:
        start_time = time.time()

        validated_input = tool_request.tool_input
        handler = self._dispatch.get(type(validated_input))

        if handler is None:
            return self._create_error_response(
                f"Unsupported GitHub repo tool input type: {type(validated_input).__name__}",
                start_time
            )

        operation = getattr(validated_input, 'operation', 'unknown')
        logger.info(f"GitHub Repo Tool - operation={operation}")

        try:
            output = await handler(validated_input)
            self._log_output(output)
            return self._create_success_response(output.model_dump(), start_time)
        except GitHubToolError as e:
            logger.warning(f"GitHub repo tool rejected {operation}: {e.message}")
            output = GitHubRepoToolOutput(
                operation=operation,
                repository=self._repo_label(validated_input),
                api_error=e.message,
                api_status_code=e.status_code
            )
            return self._create_success_response(output.model_dump(), start_time)
        except Exception as e:
            logger.error(f"GitHub repo tool error during {operation}: {e}")
            return self._create_error_response(str(e), start_time)

    # ------------------------------------------------------------------
    # Operations
    # ------------------------------------------------------------------

    async def _get_repo(self, vi: GitHubRepoGetInput) -> GitHubRepoToolOutput:
        full_name = self.client.check_repo(vi.owner, vi.repo)

        response = await self.client.call(
            self.client.gh.rest.repos.async_get,
            vi.owner, vi.repo, context=f"get_repo {full_name}"
        )

        data = response.json() or {}
        return GitHubRepoToolOutput(
            operation='get_repo',
            repository=full_name,
            repository_info=GitHubRepository(
                full_name=data.get('full_name') or full_name,
                name=data.get('name'),
                owner=(data.get('owner') or {}).get('login'),
                private=data.get('private'),
                description=data.get('description'),
                default_branch=data.get('default_branch'),
                html_url=data.get('html_url'),
                language=data.get('language'),
                topics=data.get('topics') or [],
                open_issues_count=data.get('open_issues_count'),
                archived=data.get('archived'),
                disabled=data.get('disabled'),
                has_issues=data.get('has_issues'),
                created_at=data.get('created_at'),
                updated_at=data.get('updated_at'),
                pushed_at=data.get('pushed_at'),
            ),
            rate_limit_remaining=rate_limit_remaining(response)
        )

    async def _get_file_contents(self, vi: GitHubGetFileInput) -> GitHubRepoToolOutput:
        full_name = self.client.check_repo(vi.owner, vi.repo)

        kwargs: Dict[str, Any] = {}
        if vi.ref:
            kwargs['ref'] = vi.ref

        response = await self.client.call(
            self.client.gh.rest.repos.async_get_content,
            vi.owner, vi.repo, vi.path,
            context=f"get_file_contents {full_name}:{vi.path}", **kwargs
        )

        data = response.json()

        # A directory comes back as a list; keep it to names so a large tree does
        # not swamp the caller.
        if isinstance(data, list):
            file_out = GitHubFileContent(
                path=vi.path, type='dir',
                entries=[e.get('name') for e in data if e.get('name')]
            )
        else:
            file_out = self._map_file_content(data or {}, vi.max_chars or 20000)

        return GitHubRepoToolOutput(
            operation='get_file_contents',
            repository=full_name,
            file=file_out,
            returned_count=1,
            rate_limit_remaining=rate_limit_remaining(response)
        )

    async def _list_branches(self, vi: GitHubListBranchesInput) -> GitHubRepoToolOutput:
        full_name = self.client.check_repo(vi.owner, vi.repo)
        max_results = vi.max_results or 50

        kwargs: Dict[str, Any] = {'per_page': min(max_results, 100)}
        if vi.page:
            kwargs['page'] = vi.page
        if vi.protected_only is not None:
            kwargs['protected'] = vi.protected_only

        response = await self.client.call(
            self.client.gh.rest.repos.async_list_branches,
            vi.owner, vi.repo, context=f"list_branches {full_name}", **kwargs
        )

        default_branch = await self._default_branch(full_name, vi.owner, vi.repo)
        raw = response.json() or []
        branches = [GitHubBranch(
            name=b.get('name') or '',
            sha=(b.get('commit') or {}).get('sha'),
            protected=b.get('protected'),
            is_default=(b.get('name') == default_branch),
        ) for b in raw]

        return GitHubRepoToolOutput(
            operation='list_branches',
            repository=full_name,
            branches=branches[:max_results],
            returned_count=len(branches[:max_results]),
            truncated=has_next_page(response),
            next_page=((vi.page or 1) + 1) if has_next_page(response) else None,
            rate_limit_remaining=rate_limit_remaining(response)
        )

    async def _list_commits(self, vi: GitHubListCommitsInput) -> GitHubRepoToolOutput:
        full_name = self.client.check_repo(vi.owner, vi.repo)
        max_results = vi.max_results or 30

        kwargs: Dict[str, Any] = {'per_page': min(max_results, 100)}
        if vi.ref:
            kwargs['sha'] = vi.ref
        if vi.path:
            kwargs['path'] = vi.path
        if vi.author:
            kwargs['author'] = vi.author
        if vi.page:
            kwargs['page'] = vi.page
        for field, value in (('since', vi.since), ('until', vi.until)):
            if value:
                try:
                    kwargs[field] = datetime.fromisoformat(value.replace('Z', '+00:00'))
                except ValueError:
                    raise GitHubToolError(
                        f"Invalid {field} {value!r}: expected ISO 8601, "
                        f"e.g. '2026-08-01T00:00:00Z'"
                    )

        response = await self.client.call(
            self.client.gh.rest.repos.async_list_commits,
            vi.owner, vi.repo, context=f"list_commits {full_name}", **kwargs
        )

        raw = response.json() or []
        commits = [self._map_commit(c) for c in raw]

        return GitHubRepoToolOutput(
            operation='list_commits',
            repository=full_name,
            commits=commits[:max_results],
            returned_count=len(commits[:max_results]),
            truncated=has_next_page(response),
            next_page=((vi.page or 1) + 1) if has_next_page(response) else None,
            rate_limit_remaining=rate_limit_remaining(response)
        )

    async def _compare_refs(self, vi: GitHubCompareRefsInput) -> GitHubRepoToolOutput:
        full_name = self.client.check_repo(vi.owner, vi.repo)
        max_files = vi.max_files or 50

        response = await self.client.call(
            self.client.gh.rest.repos.async_compare_commits,
            vi.owner, vi.repo, f"{vi.base}...{vi.head}",
            per_page=min(max_files, 100),
            context=f"compare_refs {full_name} {vi.base}...{vi.head}"
        )

        raw = response.json() or {}
        files = []
        for f in (raw.get('files') or [])[:max_files]:
            entry = {
                'filename': f.get('filename'),
                'status': f.get('status'),
                'additions': f.get('additions'),
                'deletions': f.get('deletions'),
            }
            if vi.include_patch and f.get('patch'):
                patch = f['patch']
                entry['patch'] = patch[:MAX_PATCH_CHARS]
                entry['patch_truncated'] = len(patch) > MAX_PATCH_CHARS
            files.append(entry)

        return GitHubRepoToolOutput(
            operation='compare_refs',
            repository=full_name,
            comparison=GitHubComparison(
                status=raw.get('status'),
                ahead_by=raw.get('ahead_by'),
                behind_by=raw.get('behind_by'),
                total_commits=raw.get('total_commits'),
                files_changed=len(raw.get('files') or []),
            ),
            commits=[self._map_commit(c) for c in (raw.get('commits') or [])][:max_files],
            files=files,
            returned_count=len(files),
            truncated=len(raw.get('files') or []) > max_files,
            rate_limit_remaining=rate_limit_remaining(response)
        )

    async def _get_commit(self, vi: GitHubGetCommitInput) -> GitHubRepoToolOutput:
        full_name = self.client.check_repo(vi.owner, vi.repo)
        max_files = vi.max_files or 50

        response = await self.client.call(
            self.client.gh.rest.repos.async_get_commit,
            vi.owner, vi.repo, vi.ref, per_page=min(max_files, 100),
            context=f"get_commit {full_name}@{vi.ref}"
        )

        raw = response.json() or {}
        files = []
        for f in (raw.get('files') or [])[:max_files]:
            entry = {
                'filename': f.get('filename'),
                'status': f.get('status'),
                'additions': f.get('additions'),
                'deletions': f.get('deletions'),
            }
            if vi.include_patch and f.get('patch'):
                patch = f['patch']
                entry['patch'] = patch[:MAX_PATCH_CHARS]
                entry['patch_truncated'] = len(patch) > MAX_PATCH_CHARS
            files.append(entry)

        return GitHubRepoToolOutput(
            operation='get_commit',
            repository=full_name,
            commit=self._map_commit(raw),
            files=files,
            returned_count=len(files),
            truncated=len(raw.get('files') or []) > max_files,
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

    @staticmethod
    def _map_commit(data: dict) -> GitHubCommit:
        commit = data.get('commit') or {}
        author = data.get('author') or {}
        return GitHubCommit(
            sha=data.get('sha') or '',
            message=commit.get('message'),
            author=author.get('login') or (commit.get('author') or {}).get('name'),
            date=(commit.get('author') or {}).get('date'),
            html_url=data.get('html_url'),
        )

    @staticmethod
    def _map_file_content(data: dict, max_chars: int) -> GitHubFileContent:
        raw = data.get('content')
        text = None
        truncated = False
        is_binary = False

        if raw and data.get('encoding') == 'base64':
            try:
                decoded = base64.b64decode(raw)
            except (binascii.Error, ValueError):
                decoded = b''
            try:
                text = decoded.decode('utf-8')
            except UnicodeDecodeError:
                # Binary file: report it rather than returning mojibake.
                is_binary = True
                text = None

        if text is not None and len(text) > max_chars:
            text = text[:max_chars] + f"\n\n[truncated at {max_chars} characters]"
            truncated = True

        return GitHubFileContent(
            path=data.get('path') or '',
            type=data.get('type'),
            size=data.get('size'),
            sha=data.get('sha'),
            content=text,
            content_truncated=truncated,
            is_binary=is_binary,
            html_url=data.get('html_url'),
        )

    @staticmethod
    def _repo_label(validated_input: Any) -> Optional[str]:
        owner = getattr(validated_input, 'owner', None)
        repo = getattr(validated_input, 'repo', None)
        return f"{owner}/{repo}" if owner and repo else None

    @staticmethod
    def _log_output(output: GitHubRepoToolOutput) -> None:
        logger.info("=" * 80)
        logger.info(f"GITHUB REPO TOOL - {output.operation}")
        logger.info("=" * 80)
        info = output.repository_info
        if info:
            logger.info(f"{info.full_name}  private={info.private}  "
                        f"default_branch={info.default_branch}")
            logger.info(f"  has_issues={info.has_issues}  archived={info.archived}  "
                        f"open_issues_count={info.open_issues_count}")
        if output.file:
            f = output.file
            logger.info(f"{f.type}: {f.path} size={f.size} binary={f.is_binary} "
                        f"truncated={f.content_truncated} entries={len(f.entries)}")
        if output.branches:
            logger.info(f"Branches: {[b.name for b in output.branches]}")
        if output.commits:
            logger.info(f"Commits: {len(output.commits)}")
        if output.commit:
            logger.info(f"Commit {output.commit.sha[:7]}: {(output.commit.message or '')[:60]}")
        if output.comparison:
            c = output.comparison
            logger.info(f"Comparison: {c.status} ahead={c.ahead_by} behind={c.behind_by} "
                        f"files={c.files_changed}")
        logger.info(f"Rate limit remaining: {output.rate_limit_remaining}")
        logger.info("=" * 80)
