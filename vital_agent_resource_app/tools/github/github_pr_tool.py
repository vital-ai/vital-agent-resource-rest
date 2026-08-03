import logging
import time
from typing import Any, Dict, List, Optional

from vital_agent_resource_app.tools.abstract_tool import AbstractTool
from vital_agent_resource_app.tools.tool_request import ToolRequest
from vital_agent_resource_app.tools.tool_response import ToolResponse
from vital_agent_resource_app.tools.github.github_client import (
    GitHubClient, GitHubToolError, rate_limit_remaining, has_next_page
)
from vital_agent_resource_app.tools.github.pr_models import (
    GitHubPRListInput, GitHubPRGetInput, GitHubPRCreateInput, GitHubPRUpdateInput,
    GitHubPRFilesInput, GitHubPRCommentListInput, GitHubPRCommentCreateInput,
    GitHubPRReviewListInput, GitHubPRReviewCreateInput, GitHubPRMergeInput,
    GitHubPullRequest, GitHubPRFile, GitHubPRReview, GitHubPRComment,
    GitHubPRMergeResult, GitHubPRToolOutput
)

logger = logging.getLogger("VitalAgentContainerLogger")

# Patches are unbounded; cap them well below the body limit.
MAX_PATCH_CHARS = 2000


class GitHubPRTool(AbstractTool):
    """GitHub pull request operations.

    Merging and approving are gated behind allow_pr_merge (default off) because
    both can put code on a protected branch; everything else rides on
    allow_writes like the issue tool.
    """

    def __init__(self, config: dict, client: GitHubClient):
        super().__init__(config or {})
        self.client = client
        self._dispatch = {
            GitHubPRListInput: self._list_prs,
            GitHubPRGetInput: self._get_pr,
            GitHubPRCreateInput: self._create_pr,
            GitHubPRUpdateInput: self._update_pr,
            GitHubPRFilesInput: self._list_pr_files,
            GitHubPRCommentListInput: self._list_pr_comments,
            GitHubPRCommentCreateInput: self._add_pr_comment,
            GitHubPRReviewListInput: self._list_pr_reviews,
            GitHubPRReviewCreateInput: self._create_pr_review,
            GitHubPRMergeInput: self._merge_pr,
        }

    def get_examples(self) -> List[Dict[str, Any]]:
        """Return list of example requests for the GitHub PR tool"""
        return [
            {
                "tool": "github_pr_tool",
                "tool_input": {
                    "operation": "list_prs",
                    "owner": "vital-ai",
                    "repo": "vital-ai-sandbox",
                    "state": "open"
                }
            },
            {
                "tool": "github_pr_tool",
                "tool_input": {
                    "operation": "create_pr",
                    "owner": "vital-ai",
                    "repo": "vital-ai-sandbox",
                    "title": "Fix flaky test",
                    "head": "fix/flaky-test",
                    "base": "main",
                    "body": "Adds a retry around the list assertion."
                }
            },
            {
                "tool": "github_pr_tool",
                "tool_input": {
                    "operation": "list_pr_files",
                    "owner": "vital-ai",
                    "repo": "vital-ai-sandbox",
                    "pr_number": 1
                }
            },
            {
                "tool": "github_pr_tool",
                "tool_input": {
                    "operation": "create_pr_review",
                    "owner": "vital-ai",
                    "repo": "vital-ai-sandbox",
                    "pr_number": 1,
                    "event": "COMMENT",
                    "body": "Looks reasonable; one question inline."
                }
            }
        ]

    async def handle_tool_request(self, tool_request: ToolRequest) -> ToolResponse:
        start_time = time.time()

        validated_input = tool_request.tool_input
        handler = self._dispatch.get(type(validated_input))

        if handler is None:
            return self._create_error_response(
                f"Unsupported GitHub PR tool input type: {type(validated_input).__name__}",
                start_time
            )

        operation = getattr(validated_input, 'operation', 'unknown')
        logger.info(f"GitHub PR Tool - operation={operation}")

        try:
            output = await handler(validated_input)
            self._log_output(output)
            return self._create_success_response(output.dict(), start_time)
        except GitHubToolError as e:
            logger.warning(f"GitHub PR tool rejected {operation}: {e.message}")
            output = GitHubPRToolOutput(
                operation=operation,
                repository=self._repo_label(validated_input),
                api_error=e.message,
                api_status_code=e.status_code
            )
            return self._create_success_response(output.dict(), start_time)
        except Exception as e:
            logger.error(f"GitHub PR tool error during {operation}: {e}")
            return self._create_error_response(str(e), start_time)

    # ------------------------------------------------------------------
    # Operations
    # ------------------------------------------------------------------

    async def _list_prs(self, vi: GitHubPRListInput) -> GitHubPRToolOutput:
        full_name = self.client.check_repo(vi.owner, vi.repo)
        max_results = vi.max_results or 30

        kwargs: Dict[str, Any] = {
            'state': vi.state or 'open',
            'sort': vi.sort or 'created',
            'direction': vi.direction or 'desc',
            'per_page': min(max_results, 100),
        }
        if vi.head:
            kwargs['head'] = vi.head
        if vi.base:
            kwargs['base'] = vi.base
        if vi.page:
            kwargs['page'] = vi.page

        response = await self.client.call(
            self.client.gh.rest.pulls.async_list,
            vi.owner, vi.repo, context=f"list_prs {full_name}", **kwargs
        )

        raw = response.json() or []
        prs = [self._map_pr(item) for item in raw]
        truncated = len(prs) > max_results or has_next_page(response)

        return GitHubPRToolOutput(
            operation='list_prs',
            repository=full_name,
            pull_requests=prs[:max_results],
            total_count=len(prs[:max_results]),
            truncated=truncated,
            rate_limit_remaining=rate_limit_remaining(response)
        )

    async def _get_pr(self, vi: GitHubPRGetInput) -> GitHubPRToolOutput:
        full_name = self.client.check_repo(vi.owner, vi.repo)
        response = await self.client.call(
            self.client.gh.rest.pulls.async_get,
            vi.owner, vi.repo, vi.pr_number,
            context=f"get_pr {full_name}#{vi.pr_number}"
        )
        return GitHubPRToolOutput(
            operation='get_pr',
            repository=full_name,
            pull_request=self._map_pr(response.json()),
            rate_limit_remaining=rate_limit_remaining(response)
        )

    async def _create_pr(self, vi: GitHubPRCreateInput) -> GitHubPRToolOutput:
        full_name = self.client.check_repo(vi.owner, vi.repo)
        self.client.check_write_allowed('create_pr')

        data: Dict[str, Any] = {'title': vi.title, 'head': vi.head, 'base': vi.base}
        if vi.body is not None:
            data['body'] = vi.body
        if vi.draft is not None:
            data['draft'] = vi.draft
        if vi.maintainer_can_modify is not None:
            data['maintainer_can_modify'] = vi.maintainer_can_modify

        response = await self.client.call(
            self.client.gh.rest.pulls.async_create,
            vi.owner, vi.repo, data=data, context=f"create_pr {full_name}"
        )
        return GitHubPRToolOutput(
            operation='create_pr',
            repository=full_name,
            pull_request=self._map_pr(response.json()),
            rate_limit_remaining=rate_limit_remaining(response)
        )

    async def _update_pr(self, vi: GitHubPRUpdateInput) -> GitHubPRToolOutput:
        full_name = self.client.check_repo(vi.owner, vi.repo)
        self.client.check_write_allowed('update_pr')

        data: Dict[str, Any] = {}
        for field in ('title', 'body', 'state', 'base'):
            value = getattr(vi, field)
            if value is not None:
                data[field] = value

        if not data:
            raise GitHubToolError(
                "update_pr requires at least one field to change (title, body, state, or base)."
            )

        response = await self.client.call(
            self.client.gh.rest.pulls.async_update,
            vi.owner, vi.repo, vi.pr_number, data=data,
            context=f"update_pr {full_name}#{vi.pr_number}"
        )
        return GitHubPRToolOutput(
            operation='update_pr',
            repository=full_name,
            pull_request=self._map_pr(response.json()),
            rate_limit_remaining=rate_limit_remaining(response)
        )

    async def _list_pr_files(self, vi: GitHubPRFilesInput) -> GitHubPRToolOutput:
        full_name = self.client.check_repo(vi.owner, vi.repo)
        max_results = vi.max_results or 50

        kwargs: Dict[str, Any] = {'per_page': min(max_results, 100)}
        if vi.page:
            kwargs['page'] = vi.page

        response = await self.client.call(
            self.client.gh.rest.pulls.async_list_files,
            vi.owner, vi.repo, vi.pr_number,
            context=f"list_pr_files {full_name}#{vi.pr_number}", **kwargs
        )

        raw = response.json() or []
        files = [self._map_file(item, vi.include_patch) for item in raw]
        truncated = len(files) > max_results or has_next_page(response)

        return GitHubPRToolOutput(
            operation='list_pr_files',
            repository=full_name,
            files=files[:max_results],
            total_count=len(files[:max_results]),
            truncated=truncated,
            rate_limit_remaining=rate_limit_remaining(response)
        )

    async def _list_pr_comments(self, vi: GitHubPRCommentListInput) -> GitHubPRToolOutput:
        full_name = self.client.check_repo(vi.owner, vi.repo)
        max_results = vi.max_results or 30

        kwargs: Dict[str, Any] = {'per_page': min(max_results, 100)}
        if vi.page:
            kwargs['page'] = vi.page

        # PR conversation comments live on the issues endpoint -- a PR is an issue.
        response = await self.client.call(
            self.client.gh.rest.issues.async_list_comments,
            vi.owner, vi.repo, vi.pr_number,
            context=f"list_pr_comments {full_name}#{vi.pr_number}", **kwargs
        )

        raw = response.json() or []
        comments = [self._map_comment(item) for item in raw]
        truncated = len(comments) > max_results or has_next_page(response)

        return GitHubPRToolOutput(
            operation='list_pr_comments',
            repository=full_name,
            comments=comments[:max_results],
            total_count=len(comments[:max_results]),
            truncated=truncated,
            rate_limit_remaining=rate_limit_remaining(response)
        )

    async def _add_pr_comment(self, vi: GitHubPRCommentCreateInput) -> GitHubPRToolOutput:
        full_name = self.client.check_repo(vi.owner, vi.repo)
        self.client.check_write_allowed('add_pr_comment')

        response = await self.client.call(
            self.client.gh.rest.issues.async_create_comment,
            vi.owner, vi.repo, vi.pr_number, data={'body': vi.body},
            context=f"add_pr_comment {full_name}#{vi.pr_number}"
        )
        return GitHubPRToolOutput(
            operation='add_pr_comment',
            repository=full_name,
            comment=self._map_comment(response.json()),
            rate_limit_remaining=rate_limit_remaining(response)
        )

    async def _list_pr_reviews(self, vi: GitHubPRReviewListInput) -> GitHubPRToolOutput:
        full_name = self.client.check_repo(vi.owner, vi.repo)
        max_results = vi.max_results or 30

        response = await self.client.call(
            self.client.gh.rest.pulls.async_list_reviews,
            vi.owner, vi.repo, vi.pr_number, per_page=min(max_results, 100),
            context=f"list_pr_reviews {full_name}#{vi.pr_number}"
        )

        raw = response.json() or []
        reviews = [self._map_review(item) for item in raw]
        truncated = len(reviews) > max_results or has_next_page(response)

        return GitHubPRToolOutput(
            operation='list_pr_reviews',
            repository=full_name,
            reviews=reviews[:max_results],
            total_count=len(reviews[:max_results]),
            truncated=truncated,
            rate_limit_remaining=rate_limit_remaining(response)
        )

    async def _create_pr_review(self, vi: GitHubPRReviewCreateInput) -> GitHubPRToolOutput:
        full_name = self.client.check_repo(vi.owner, vi.repo)

        # An approving review can satisfy branch protection and unblock a merge,
        # so it shares the merge gate rather than the general write gate.
        gate = 'allow_pr_merge' if vi.event == 'APPROVE' else 'allow_writes'
        self.client.check_write_allowed(f"create_pr_review({vi.event})", gate=gate)

        if vi.event in ('REQUEST_CHANGES', 'COMMENT') and not vi.body:
            raise GitHubToolError(
                f"A review body is required when event is {vi.event}."
            )

        data: Dict[str, Any] = {'event': vi.event}
        if vi.body:
            data['body'] = vi.body

        response = await self.client.call(
            self.client.gh.rest.pulls.async_create_review,
            vi.owner, vi.repo, vi.pr_number, data=data,
            context=f"create_pr_review {full_name}#{vi.pr_number}"
        )
        return GitHubPRToolOutput(
            operation='create_pr_review',
            repository=full_name,
            review=self._map_review(response.json()),
            rate_limit_remaining=rate_limit_remaining(response)
        )

    async def _merge_pr(self, vi: GitHubPRMergeInput) -> GitHubPRToolOutput:
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
        return GitHubPRToolOutput(
            operation='merge_pr',
            repository=full_name,
            merge_result=GitHubPRMergeResult(
                merged=bool(raw.get('merged')),
                sha=raw.get('sha'),
                message=raw.get('message')
            ),
            rate_limit_remaining=rate_limit_remaining(response)
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _repo_label(validated_input: Any) -> Optional[str]:
        owner = getattr(validated_input, 'owner', None)
        repo = getattr(validated_input, 'repo', None)
        return f"{owner}/{repo}" if owner and repo else None

    def _truncate(self, text: Optional[str], limit: Optional[int] = None) -> tuple:
        if not text:
            return text, False
        limit = limit or self.client.max_body_chars
        if len(text) <= limit:
            return text, False
        return text[:limit] + f"\n\n[truncated at {limit} characters]", True

    def _map_pr(self, data: Optional[dict]) -> Optional[GitHubPullRequest]:
        if not data:
            return None
        body, body_truncated = self._truncate(data.get('body'))
        head = data.get('head') or {}
        base = data.get('base') or {}
        return GitHubPullRequest(
            number=data.get('number'),
            title=data.get('title') or '',
            state=data.get('state') or '',
            draft=bool(data.get('draft')),
            body=body,
            body_truncated=body_truncated,
            html_url=data.get('html_url') or '',
            user=(data.get('user') or {}).get('login'),
            head=head.get('ref'),
            base=base.get('ref'),
            head_sha=head.get('sha'),
            merged=bool(data.get('merged')),
            mergeable=data.get('mergeable'),
            mergeable_state=data.get('mergeable_state'),
            merged_at=data.get('merged_at'),
            labels=[(l.get('name') if isinstance(l, dict) else str(l))
                    for l in (data.get('labels') or [])],
            assignees=[a.get('login') for a in (data.get('assignees') or []) if a.get('login')],
            requested_reviewers=[r.get('login') for r in (data.get('requested_reviewers') or [])
                                 if r.get('login')],
            comments=data.get('comments'),
            review_comments=data.get('review_comments'),
            commits=data.get('commits'),
            additions=data.get('additions'),
            deletions=data.get('deletions'),
            changed_files=data.get('changed_files'),
            created_at=data.get('created_at'),
            updated_at=data.get('updated_at'),
            closed_at=data.get('closed_at')
        )

    def _map_file(self, data: dict, include_patch: bool) -> GitHubPRFile:
        patch = None
        patch_truncated = False
        if include_patch:
            patch, patch_truncated = self._truncate(data.get('patch'), MAX_PATCH_CHARS)
        return GitHubPRFile(
            filename=data.get('filename') or '',
            status=data.get('status'),
            additions=data.get('additions') or 0,
            deletions=data.get('deletions') or 0,
            changes=data.get('changes') or 0,
            previous_filename=data.get('previous_filename'),
            patch=patch,
            patch_truncated=patch_truncated
        )

    def _map_review(self, data: Optional[dict]) -> Optional[GitHubPRReview]:
        if not data:
            return None
        body, body_truncated = self._truncate(data.get('body'))
        return GitHubPRReview(
            id=data.get('id'),
            user=(data.get('user') or {}).get('login'),
            state=data.get('state'),
            body=body,
            body_truncated=body_truncated,
            html_url=data.get('html_url'),
            submitted_at=data.get('submitted_at')
        )

    def _map_comment(self, data: Optional[dict]) -> Optional[GitHubPRComment]:
        if not data:
            return None
        body, body_truncated = self._truncate(data.get('body'))
        return GitHubPRComment(
            id=data.get('id'),
            body=body,
            body_truncated=body_truncated,
            user=(data.get('user') or {}).get('login'),
            html_url=data.get('html_url'),
            created_at=data.get('created_at'),
            updated_at=data.get('updated_at')
        )

    @staticmethod
    def _log_output(output: GitHubPRToolOutput) -> None:
        logger.info("=" * 80)
        logger.info(f"GITHUB PR TOOL - {output.operation}")
        logger.info("=" * 80)
        logger.info(f"Repository: {output.repository}")

        if output.pull_request:
            pr = output.pull_request
            logger.info(f"PR #{pr.number}: [{pr.state}] {pr.title}")
            logger.info(f"  {pr.head} -> {pr.base}  merged={pr.merged}  draft={pr.draft}")
            logger.info(f"  URL: {pr.html_url}")

        if output.pull_requests:
            logger.info(f"PRs returned: {len(output.pull_requests)} (truncated={output.truncated})")
            for pr in output.pull_requests:
                logger.info(f"  #{pr.number} [{pr.state}] {pr.title} ({pr.head} -> {pr.base})")

        if output.files:
            logger.info(f"Files changed: {len(output.files)}")
            for f in output.files:
                logger.info(f"  {f.status}: {f.filename} (+{f.additions}/-{f.deletions})")

        if output.reviews:
            logger.info(f"Reviews: {[(r.user, r.state) for r in output.reviews]}")

        if output.review:
            logger.info(f"Review submitted: {output.review.state} by {output.review.user}")

        if output.merge_result:
            logger.info(f"Merge: merged={output.merge_result.merged} sha={output.merge_result.sha}")

        logger.info(f"Rate limit remaining: {output.rate_limit_remaining}")
        logger.info("=" * 80)
