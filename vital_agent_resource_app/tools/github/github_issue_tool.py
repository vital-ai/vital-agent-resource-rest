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
from vital_agent_resource_app.tools.github.issue_models import (
    GitHubIssueListInput, GitHubIssueGetInput, GitHubIssueCreateInput,
    GitHubIssueUpdateInput, GitHubIssueCloseInput, GitHubIssueReopenInput,
    GitHubIssueCommentListInput, GitHubIssueCommentCreateInput,
    GitHubIssueCommentUpdateInput, GitHubIssueCommentDeleteInput,
    GitHubIssueAddLabelsInput, GitHubIssueRemoveLabelsInput,
    GitHubIssueAddAssigneesInput, GitHubIssueRemoveAssigneesInput,
    GitHubIssueSearchInput,
    GitHubIssue, GitHubComment, GitHubIssueToolOutput
)

logger = logging.getLogger("VitalAgentContainerLogger")


def _parse_since(value: Optional[str]) -> Optional[datetime]:
    """Parse an ISO 8601 timestamp; githubkit expects a datetime for `since`."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        raise GitHubToolError(
            f"Invalid timestamp {value!r}: expected ISO 8601, e.g. '2026-08-01T00:00:00Z'"
        )


class GitHubIssueTool(AbstractTool):
    """GitHub issue operations.

    GitHub's REST API has no delete-issue endpoint, so `close_issue` is the
    delete-equivalent. Issue comments can be deleted outright.
    """

    def __init__(self, config: dict, client: GitHubClient):
        super().__init__(config or {})
        self.client = client
        self._dispatch = {
            GitHubIssueListInput: self._list_issues,
            GitHubIssueGetInput: self._get_issue,
            GitHubIssueCreateInput: self._create_issue,
            GitHubIssueUpdateInput: self._update_issue,
            GitHubIssueCloseInput: self._close_issue,
            GitHubIssueReopenInput: self._reopen_issue,
            GitHubIssueCommentListInput: self._list_comments,
            GitHubIssueCommentCreateInput: self._add_comment,
            GitHubIssueCommentUpdateInput: self._update_comment,
            GitHubIssueCommentDeleteInput: self._delete_comment,
            GitHubIssueAddLabelsInput: self._add_labels,
            GitHubIssueRemoveLabelsInput: self._remove_labels,
            GitHubIssueAddAssigneesInput: self._add_assignees,
            GitHubIssueRemoveAssigneesInput: self._remove_assignees,
            GitHubIssueSearchInput: self._search_issues,
        }

    def get_examples(self) -> List[Dict[str, Any]]:
        """Return list of example requests for the GitHub issue tool"""
        return [
            {
                "tool": "github_issue_tool",
                "tool_input": {
                    "operation": "list_issues",
                    "owner": "vital-ai",
                    "repo": "vital-ai-sandbox",
                    "state": "open",
                    "max_results": 10
                }
            },
            {
                "tool": "github_issue_tool",
                "tool_input": {
                    "operation": "create_issue",
                    "owner": "vital-ai",
                    "repo": "vital-ai-sandbox",
                    "title": "Investigate flaky web search test",
                    "body": "The client test fails intermittently on CI.",
                    "labels": ["bug"]
                }
            },
            {
                "tool": "github_issue_tool",
                "tool_input": {
                    "operation": "add_comment",
                    "owner": "vital-ai",
                    "repo": "vital-ai-sandbox",
                    "issue_number": 1,
                    "body": "Reproduced locally; looks like a timeout."
                }
            },
            {
                "tool": "github_issue_tool",
                "tool_input": {
                    "operation": "close_issue",
                    "owner": "vital-ai",
                    "repo": "vital-ai-sandbox",
                    "issue_number": 1,
                    "state_reason": "completed"
                }
            },
            {
                "tool": "github_issue_tool",
                "tool_input": {
                    "operation": "search_issues",
                    "owner": "vital-ai",
                    "repo": "vital-ai-sandbox",
                    "query": "is:open label:bug timeout",
                    "max_results": 10
                }
            }
        ]

    async def handle_tool_request(self, tool_request: ToolRequest) -> ToolResponse:
        start_time = time.time()

        validated_input = tool_request.tool_input
        handler = self._dispatch.get(type(validated_input))

        if handler is None:
            return self._create_error_response(
                f"Unsupported GitHub issue tool input type: {type(validated_input).__name__}",
                start_time
            )

        operation = getattr(validated_input, 'operation', 'unknown')
        logger.info(f"GitHub Issue Tool - operation={operation}")

        try:
            output = await handler(validated_input)
            self._log_output(output)
            return self._create_success_response(output.dict(), start_time)
        except GitHubToolError as e:
            # Expected failures (config, allowlist, gates, GitHub API errors) come
            # back as structured output so the agent can read the reason.
            logger.warning(f"GitHub issue tool rejected {operation}: {e.message}")
            output = GitHubIssueToolOutput(
                operation=operation,
                repository=self._repo_label(validated_input),
                api_error=e.message,
                api_status_code=e.status_code
            )
            return self._create_success_response(output.dict(), start_time)
        except Exception as e:
            logger.error(f"GitHub issue tool error during {operation}: {e}")
            return self._create_error_response(str(e), start_time)

    # ------------------------------------------------------------------
    # Operations
    # ------------------------------------------------------------------

    async def _list_issues(self, vi: GitHubIssueListInput) -> GitHubIssueToolOutput:
        full_name = self.client.check_repo(vi.owner, vi.repo)
        max_results = vi.max_results or 30

        kwargs: Dict[str, Any] = {
            'state': vi.state or 'open',
            'sort': vi.sort or 'created',
            'direction': vi.direction or 'desc',
            'per_page': min(max_results, 100),
        }
        if vi.labels:
            kwargs['labels'] = ','.join(vi.labels)
        if vi.assignee:
            kwargs['assignee'] = vi.assignee
        if vi.creator:
            kwargs['creator'] = vi.creator
        if vi.milestone:
            kwargs['milestone'] = vi.milestone
        if vi.page:
            kwargs['page'] = vi.page
        since = _parse_since(vi.since)
        if since:
            kwargs['since'] = since

        response = await self.client.call(
            self.client.gh.rest.issues.async_list_for_repo,
            vi.owner, vi.repo, context=f"list_issues {full_name}", **kwargs
        )

        raw = response.json() or []
        issues = [self._map_issue(item) for item in raw]

        # GitHub returns pull requests from the issues endpoint. Filter before
        # truncating so max_results counts actual issues.
        if not vi.include_pull_requests:
            issues = [i for i in issues if not i.is_pull_request]

        truncated = len(issues) > max_results or has_next_page(response)
        issues = issues[:max_results]

        return GitHubIssueToolOutput(
            operation='list_issues',
            repository=full_name,
            issues=issues,
            total_count=len(issues),
            truncated=truncated,
            rate_limit_remaining=rate_limit_remaining(response)
        )

    async def _get_issue(self, vi: GitHubIssueGetInput) -> GitHubIssueToolOutput:
        full_name = self.client.check_repo(vi.owner, vi.repo)
        response = await self.client.call(
            self.client.gh.rest.issues.async_get,
            vi.owner, vi.repo, vi.issue_number,
            context=f"get_issue {full_name}#{vi.issue_number}"
        )
        return GitHubIssueToolOutput(
            operation='get_issue',
            repository=full_name,
            issue=self._map_issue(response.json()),
            rate_limit_remaining=rate_limit_remaining(response)
        )

    async def _create_issue(self, vi: GitHubIssueCreateInput) -> GitHubIssueToolOutput:
        full_name = self.client.check_repo(vi.owner, vi.repo)
        self.client.check_write_allowed('create_issue')

        data: Dict[str, Any] = {'title': vi.title}
        if vi.body is not None:
            data['body'] = vi.body
        if vi.labels:
            data['labels'] = vi.labels
        if vi.assignees:
            data['assignees'] = vi.assignees
        if vi.milestone is not None:
            data['milestone'] = vi.milestone

        response = await self.client.call(
            self.client.gh.rest.issues.async_create,
            vi.owner, vi.repo, data=data, context=f"create_issue {full_name}"
        )
        return GitHubIssueToolOutput(
            operation='create_issue',
            repository=full_name,
            issue=self._map_issue(response.json()),
            rate_limit_remaining=rate_limit_remaining(response)
        )

    async def _update_issue(self, vi: GitHubIssueUpdateInput) -> GitHubIssueToolOutput:
        full_name = self.client.check_repo(vi.owner, vi.repo)
        self.client.check_write_allowed('update_issue')

        # Only send what the caller actually set, so an update never clears a
        # field it did not mention.
        data: Dict[str, Any] = {}
        for field in ('title', 'body', 'state', 'state_reason', 'labels', 'assignees', 'milestone'):
            value = getattr(vi, field)
            if value is not None:
                data[field] = value

        if not data:
            raise GitHubToolError(
                "update_issue requires at least one field to change "
                "(title, body, state, state_reason, labels, assignees, or milestone)."
            )

        response = await self.client.call(
            self.client.gh.rest.issues.async_update,
            vi.owner, vi.repo, vi.issue_number, data=data,
            context=f"update_issue {full_name}#{vi.issue_number}"
        )
        return GitHubIssueToolOutput(
            operation='update_issue',
            repository=full_name,
            issue=self._map_issue(response.json()),
            rate_limit_remaining=rate_limit_remaining(response)
        )

    async def _close_issue(self, vi: GitHubIssueCloseInput) -> GitHubIssueToolOutput:
        full_name = self.client.check_repo(vi.owner, vi.repo)
        self.client.check_write_allowed('close_issue')

        comment_out = None
        if vi.comment:
            comment_response = await self.client.call(
                self.client.gh.rest.issues.async_create_comment,
                vi.owner, vi.repo, vi.issue_number, data={'body': vi.comment},
                context=f"close_issue comment {full_name}#{vi.issue_number}"
            )
            comment_out = self._map_comment(comment_response.json())

        response = await self.client.call(
            self.client.gh.rest.issues.async_update,
            vi.owner, vi.repo, vi.issue_number,
            data={'state': 'closed', 'state_reason': vi.state_reason or 'completed'},
            context=f"close_issue {full_name}#{vi.issue_number}"
        )
        return GitHubIssueToolOutput(
            operation='close_issue',
            repository=full_name,
            issue=self._map_issue(response.json()),
            comment=comment_out,
            rate_limit_remaining=rate_limit_remaining(response)
        )

    async def _reopen_issue(self, vi: GitHubIssueReopenInput) -> GitHubIssueToolOutput:
        full_name = self.client.check_repo(vi.owner, vi.repo)
        self.client.check_write_allowed('reopen_issue')

        response = await self.client.call(
            self.client.gh.rest.issues.async_update,
            vi.owner, vi.repo, vi.issue_number,
            data={'state': 'open', 'state_reason': 'reopened'},
            context=f"reopen_issue {full_name}#{vi.issue_number}"
        )
        return GitHubIssueToolOutput(
            operation='reopen_issue',
            repository=full_name,
            issue=self._map_issue(response.json()),
            rate_limit_remaining=rate_limit_remaining(response)
        )

    async def _list_comments(self, vi: GitHubIssueCommentListInput) -> GitHubIssueToolOutput:
        full_name = self.client.check_repo(vi.owner, vi.repo)
        max_results = vi.max_results or 30

        kwargs: Dict[str, Any] = {'per_page': min(max_results, 100)}
        if vi.page:
            kwargs['page'] = vi.page
        since = _parse_since(vi.since)
        if since:
            kwargs['since'] = since

        response = await self.client.call(
            self.client.gh.rest.issues.async_list_comments,
            vi.owner, vi.repo, vi.issue_number,
            context=f"list_comments {full_name}#{vi.issue_number}", **kwargs
        )

        raw = response.json() or []
        comments = [self._map_comment(item) for item in raw]
        truncated = len(comments) > max_results or has_next_page(response)

        return GitHubIssueToolOutput(
            operation='list_comments',
            repository=full_name,
            comments=comments[:max_results],
            total_count=len(comments[:max_results]),
            truncated=truncated,
            rate_limit_remaining=rate_limit_remaining(response)
        )

    async def _add_comment(self, vi: GitHubIssueCommentCreateInput) -> GitHubIssueToolOutput:
        full_name = self.client.check_repo(vi.owner, vi.repo)
        self.client.check_write_allowed('add_comment')

        response = await self.client.call(
            self.client.gh.rest.issues.async_create_comment,
            vi.owner, vi.repo, vi.issue_number, data={'body': vi.body},
            context=f"add_comment {full_name}#{vi.issue_number}"
        )
        return GitHubIssueToolOutput(
            operation='add_comment',
            repository=full_name,
            comment=self._map_comment(response.json()),
            rate_limit_remaining=rate_limit_remaining(response)
        )

    async def _update_comment(self, vi: GitHubIssueCommentUpdateInput) -> GitHubIssueToolOutput:
        # Comment endpoints are still repo-scoped, so the allowlist applies.
        full_name = self.client.check_repo(vi.owner, vi.repo)
        self.client.check_write_allowed('update_comment')

        response = await self.client.call(
            self.client.gh.rest.issues.async_update_comment,
            vi.owner, vi.repo, vi.comment_id, data={'body': vi.body},
            context=f"update_comment {full_name} comment {vi.comment_id}"
        )
        return GitHubIssueToolOutput(
            operation='update_comment',
            repository=full_name,
            comment=self._map_comment(response.json()),
            rate_limit_remaining=rate_limit_remaining(response)
        )

    async def _delete_comment(self, vi: GitHubIssueCommentDeleteInput) -> GitHubIssueToolOutput:
        full_name = self.client.check_repo(vi.owner, vi.repo)
        self.client.check_write_allowed('delete_comment')

        response = await self.client.call(
            self.client.gh.rest.issues.async_delete_comment,
            vi.owner, vi.repo, vi.comment_id,
            context=f"delete_comment {full_name} comment {vi.comment_id}"
        )
        return GitHubIssueToolOutput(
            operation='delete_comment',
            repository=full_name,
            deleted_id=vi.comment_id,
            rate_limit_remaining=rate_limit_remaining(response)
        )

    async def _add_labels(self, vi: GitHubIssueAddLabelsInput) -> GitHubIssueToolOutput:
        full_name = self.client.check_repo(vi.owner, vi.repo)
        self.client.check_write_allowed('add_labels')

        await self.client.call(
            self.client.gh.rest.issues.async_add_labels,
            vi.owner, vi.repo, vi.issue_number, data={'labels': vi.labels},
            context=f"add_labels {full_name}#{vi.issue_number}"
        )
        return await self._issue_result('add_labels', full_name, vi.owner, vi.repo, vi.issue_number)

    async def _remove_labels(self, vi: GitHubIssueRemoveLabelsInput) -> GitHubIssueToolOutput:
        full_name = self.client.check_repo(vi.owner, vi.repo)
        self.client.check_write_allowed('remove_labels')

        for label in vi.labels:
            try:
                await self.client.call(
                    self.client.gh.rest.issues.async_remove_label,
                    vi.owner, vi.repo, vi.issue_number, label,
                    context=f"remove_labels {full_name}#{vi.issue_number}"
                )
            except GitHubToolError as e:
                # Removing a label the issue does not carry is a no-op, not a failure.
                if e.status_code == 404:
                    logger.info(f"Label {label!r} not present on {full_name}#{vi.issue_number}; skipping")
                    continue
                raise

        return await self._issue_result('remove_labels', full_name, vi.owner, vi.repo, vi.issue_number)

    async def _add_assignees(self, vi: GitHubIssueAddAssigneesInput) -> GitHubIssueToolOutput:
        full_name = self.client.check_repo(vi.owner, vi.repo)
        self.client.check_write_allowed('add_assignees')

        response = await self.client.call(
            self.client.gh.rest.issues.async_add_assignees,
            vi.owner, vi.repo, vi.issue_number, data={'assignees': vi.assignees},
            context=f"add_assignees {full_name}#{vi.issue_number}"
        )
        return GitHubIssueToolOutput(
            operation='add_assignees',
            repository=full_name,
            issue=self._map_issue(response.json()),
            rate_limit_remaining=rate_limit_remaining(response)
        )

    async def _remove_assignees(self, vi: GitHubIssueRemoveAssigneesInput) -> GitHubIssueToolOutput:
        full_name = self.client.check_repo(vi.owner, vi.repo)
        self.client.check_write_allowed('remove_assignees')

        response = await self.client.call(
            self.client.gh.rest.issues.async_remove_assignees,
            vi.owner, vi.repo, vi.issue_number, data={'assignees': vi.assignees},
            context=f"remove_assignees {full_name}#{vi.issue_number}"
        )
        return GitHubIssueToolOutput(
            operation='remove_assignees',
            repository=full_name,
            issue=self._map_issue(response.json()),
            rate_limit_remaining=rate_limit_remaining(response)
        )

    async def _search_issues(self, vi: GitHubIssueSearchInput) -> GitHubIssueToolOutput:
        full_name = self.client.check_repo(vi.owner, vi.repo)
        max_results = vi.max_results or 30

        # /search/issues takes a query string rather than a repo path, so the
        # repo qualifier is added here rather than being structural.
        query = self.client.scoped_search_query(full_name, vi.query)

        kwargs: Dict[str, Any] = {'q': query, 'per_page': min(max_results, 100)}
        if vi.sort:
            kwargs['sort'] = vi.sort
        if vi.order:
            kwargs['order'] = vi.order
        if vi.page:
            kwargs['page'] = vi.page

        response = await self.client.call(
            self.client.gh.rest.search.async_issues_and_pull_requests,
            context=f"search_issues {full_name}", **kwargs
        )

        raw = response.json() or {}
        issues = [self._map_issue(item) for item in raw.get('items', [])]
        if not vi.include_pull_requests:
            issues = [i for i in issues if not i.is_pull_request]

        truncated = bool(raw.get('incomplete_results')) or len(issues) > max_results \
            or (raw.get('total_count') or 0) > len(issues)

        return GitHubIssueToolOutput(
            operation='search_issues',
            repository=full_name,
            issues=issues[:max_results],
            total_count=raw.get('total_count'),
            truncated=truncated,
            rate_limit_remaining=rate_limit_remaining(response)
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _issue_result(self, operation: str, full_name: str, owner: str,
                            repo: str, issue_number: int) -> GitHubIssueToolOutput:
        """Re-read the issue so label operations return the same shape as the rest."""
        response = await self.client.call(
            self.client.gh.rest.issues.async_get,
            owner, repo, issue_number, context=f"{operation} refresh {full_name}#{issue_number}"
        )
        return GitHubIssueToolOutput(
            operation=operation,
            repository=full_name,
            issue=self._map_issue(response.json()),
            rate_limit_remaining=rate_limit_remaining(response)
        )

    @staticmethod
    def _repo_label(validated_input: Any) -> Optional[str]:
        owner = getattr(validated_input, 'owner', None)
        repo = getattr(validated_input, 'repo', None)
        return f"{owner}/{repo}" if owner and repo else None

    def _truncate(self, text: Optional[str]) -> tuple:
        """Trim long bodies -- raw GitHub bodies can be enormous."""
        if not text:
            return text, False
        limit = self.client.max_body_chars
        if len(text) <= limit:
            return text, False
        return text[:limit] + f"\n\n[truncated at {limit} characters]", True

    def _map_issue(self, data: Optional[dict]) -> Optional[GitHubIssue]:
        if not data:
            return None
        body, body_truncated = self._truncate(data.get('body'))
        milestone = data.get('milestone') or {}
        return GitHubIssue(
            number=data.get('number'),
            title=data.get('title') or '',
            state=data.get('state') or '',
            state_reason=data.get('state_reason'),
            body=body,
            body_truncated=body_truncated,
            html_url=data.get('html_url') or '',
            user=(data.get('user') or {}).get('login'),
            assignees=[a.get('login') for a in (data.get('assignees') or []) if a.get('login')],
            labels=[self._label_name(label) for label in (data.get('labels') or [])],
            milestone=milestone.get('title') if isinstance(milestone, dict) else None,
            comments=data.get('comments') or 0,
            created_at=data.get('created_at'),
            updated_at=data.get('updated_at'),
            closed_at=data.get('closed_at'),
            is_pull_request='pull_request' in data
        )

    @staticmethod
    def _label_name(label: Any) -> str:
        # GitHub returns labels as objects, but the schema also permits bare strings.
        if isinstance(label, dict):
            return label.get('name') or ''
        return str(label)

    def _map_comment(self, data: Optional[dict]) -> Optional[GitHubComment]:
        if not data:
            return None
        body, body_truncated = self._truncate(data.get('body'))
        return GitHubComment(
            id=data.get('id'),
            body=body,
            body_truncated=body_truncated,
            user=(data.get('user') or {}).get('login'),
            html_url=data.get('html_url'),
            created_at=data.get('created_at'),
            updated_at=data.get('updated_at')
        )

    @staticmethod
    def _log_output(output: GitHubIssueToolOutput) -> None:
        logger.info("=" * 80)
        logger.info(f"GITHUB ISSUE TOOL - {output.operation}")
        logger.info("=" * 80)
        logger.info(f"Repository: {output.repository}")

        if output.issue:
            logger.info(f"Issue #{output.issue.number}: [{output.issue.state}] {output.issue.title}")
            logger.info(f"  URL: {output.issue.html_url}")
            if output.issue.labels:
                logger.info(f"  Labels: {output.issue.labels}")
            if output.issue.assignees:
                logger.info(f"  Assignees: {output.issue.assignees}")

        if output.issues:
            logger.info(f"Issues returned: {len(output.issues)} (truncated={output.truncated})")
            for issue in output.issues:
                logger.info(f"  #{issue.number} [{issue.state}] {issue.title}")

        if output.comment:
            logger.info(f"Comment {output.comment.id} by {output.comment.user}")

        if output.comments:
            logger.info(f"Comments returned: {len(output.comments)}")

        if output.deleted_id:
            logger.info(f"Deleted id: {output.deleted_id}")

        logger.info(f"Rate limit remaining: {output.rate_limit_remaining}")
        logger.info("=" * 80)
