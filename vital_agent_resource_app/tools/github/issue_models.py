from pydantic import BaseModel, Field
from typing import List, Optional, Literal, Union

from vital_agent_resource_app.tools.github.common_models import GitHubRepoBase, GitHubOutputBase


# ---------------------------------------------------------------------------
# Input models -- one per operation, discriminated by the `operation` literal.
# ---------------------------------------------------------------------------

class GitHubIssueListInput(GitHubRepoBase):
    """List issues in a repository"""
    operation: Literal["list_issues"] = Field(..., description="Operation to perform")
    state: Optional[Literal["open", "closed", "all"]] = Field("open", description="Issue state filter")
    labels: Optional[List[str]] = Field(None, description="Only issues carrying all of these labels")
    assignee: Optional[str] = Field(None, description="Login of the assignee, or '*' / 'none'")
    creator: Optional[str] = Field(None, description="Login of the issue creator")
    milestone: Optional[str] = Field(None, description="Milestone number, '*', or 'none'")
    since: Optional[str] = Field(None, description="Only issues updated at or after this ISO 8601 timestamp")
    sort: Optional[Literal["created", "updated", "comments"]] = Field("created", description="Sort field")
    direction: Optional[Literal["asc", "desc"]] = Field("desc", description="Sort direction")
    include_pull_requests: Optional[bool] = Field(
        False,
        description="GitHub returns pull requests from the issues endpoint; set true to keep them"
    )
    max_results: Optional[int] = Field(30, description="Maximum issues to return", ge=1, le=100)
    page: Optional[int] = Field(
        None,
        description="Page to start from. This operation may consume several pages to fill "
                    "max_results after filtering out pull requests, so do not assume the "
                    "next batch is page+1 -- pass the next_page value from the response, "
                    "which may repeat a partly-consumed page and can therefore return "
                    "records you have already seen.",
        ge=1
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "operation": "list_issues",
                "owner": "vital-ai",
                "repo": "vital-ai-sandbox",
                "state": "open",
                "max_results": 10
            }
        }
    }


class GitHubIssueGetInput(GitHubRepoBase):
    """Get a single issue by number"""
    operation: Literal["get_issue"] = Field(..., description="Operation to perform")
    issue_number: int = Field(..., description="Issue number", ge=1)


class GitHubIssueCreateInput(GitHubRepoBase):
    """Create a new issue"""
    operation: Literal["create_issue"] = Field(..., description="Operation to perform")
    title: str = Field(..., description="Issue title", min_length=1)
    body: Optional[str] = Field(None, description="Issue body in Markdown")
    labels: Optional[List[str]] = Field(None, description="Labels to apply")
    assignees: Optional[List[str]] = Field(None, description="Logins to assign")
    milestone: Optional[int] = Field(None, description="Milestone number")

    model_config = {
        "json_schema_extra": {
            "example": {
                "operation": "create_issue",
                "owner": "vital-ai",
                "repo": "vital-ai-sandbox",
                "title": "Investigate flaky test",
                "body": "The web search client test fails intermittently.",
                "labels": ["bug"]
            }
        }
    }


class GitHubIssueUpdateInput(GitHubRepoBase):
    """Update an existing issue. Only the fields provided are sent to GitHub."""
    operation: Literal["update_issue"] = Field(..., description="Operation to perform")
    issue_number: int = Field(..., description="Issue number", ge=1)
    title: Optional[str] = Field(None, description="New title", min_length=1)
    body: Optional[str] = Field(None, description="New body in Markdown")
    state: Optional[Literal["open", "closed"]] = Field(None, description="New state")
    state_reason: Optional[Literal["completed", "not_planned", "reopened"]] = Field(
        None, description="Reason accompanying a state change"
    )
    labels: Optional[List[str]] = Field(None, description="Replace labels with this set")
    assignees: Optional[List[str]] = Field(None, description="Replace assignees with this set")
    milestone: Optional[int] = Field(None, description="Milestone number")


class GitHubIssueCloseInput(GitHubRepoBase):
    """Close an issue.

    GitHub's REST API has no delete-issue endpoint -- closing is the
    delete-equivalent. Deleting an issue is admin-only and not exposed here.
    """
    operation: Literal["close_issue"] = Field(..., description="Operation to perform")
    issue_number: int = Field(..., description="Issue number", ge=1)
    state_reason: Optional[Literal["completed", "not_planned", "duplicate"]] = Field(
        "completed", description="Why the issue is being closed"
    )
    comment: Optional[str] = Field(None, description="Optional comment posted before closing")


class GitHubIssueReopenInput(GitHubRepoBase):
    """Reopen a closed issue"""
    operation: Literal["reopen_issue"] = Field(..., description="Operation to perform")
    issue_number: int = Field(..., description="Issue number", ge=1)


class GitHubIssueCommentListInput(GitHubRepoBase):
    """List comments on an issue"""
    operation: Literal["list_comments"] = Field(..., description="Operation to perform")
    issue_number: int = Field(..., description="Issue number", ge=1)
    since: Optional[str] = Field(None, description="Only comments updated at or after this ISO 8601 timestamp")
    max_results: Optional[int] = Field(30, description="Maximum comments to return", ge=1, le=100)
    page: Optional[int] = Field(
        None, description="Page to fetch; this operation reads exactly one page", ge=1
    )


class GitHubIssueCommentCreateInput(GitHubRepoBase):
    """Add a comment to an issue"""
    operation: Literal["add_comment"] = Field(..., description="Operation to perform")
    issue_number: int = Field(..., description="Issue number", ge=1)
    body: str = Field(..., description="Comment body in Markdown", min_length=1)


class GitHubIssueCommentUpdateInput(GitHubRepoBase):
    """Edit an existing issue comment"""
    operation: Literal["update_comment"] = Field(..., description="Operation to perform")
    comment_id: int = Field(..., description="Comment id (not the issue number)", ge=1)
    body: str = Field(..., description="Replacement comment body", min_length=1)


class GitHubIssueCommentDeleteInput(GitHubRepoBase):
    """Delete an issue comment.

    Comments are genuinely deletable, unlike issues themselves.
    """
    operation: Literal["delete_comment"] = Field(..., description="Operation to perform")
    comment_id: int = Field(..., description="Comment id (not the issue number)", ge=1)


class GitHubIssueAddLabelsInput(GitHubRepoBase):
    """Add labels to an issue, leaving existing labels in place"""
    operation: Literal["add_labels"] = Field(..., description="Operation to perform")
    issue_number: int = Field(..., description="Issue number", ge=1)
    labels: List[str] = Field(..., description="Labels to add", min_length=1)


class GitHubIssueRemoveLabelsInput(GitHubRepoBase):
    """Remove labels from an issue"""
    operation: Literal["remove_labels"] = Field(..., description="Operation to perform")
    issue_number: int = Field(..., description="Issue number", ge=1)
    labels: List[str] = Field(..., description="Labels to remove", min_length=1)


class GitHubIssueAddAssigneesInput(GitHubRepoBase):
    """Assign users to an issue"""
    operation: Literal["add_assignees"] = Field(..., description="Operation to perform")
    issue_number: int = Field(..., description="Issue number", ge=1)
    assignees: List[str] = Field(..., description="Logins to assign", min_length=1)


class GitHubIssueRemoveAssigneesInput(GitHubRepoBase):
    """Remove assignees from an issue"""
    operation: Literal["remove_assignees"] = Field(..., description="Operation to perform")
    issue_number: int = Field(..., description="Issue number", ge=1)
    assignees: List[str] = Field(..., description="Logins to remove", min_length=1)


class GitHubIssueSearchInput(GitHubRepoBase):
    """Search issues within one repository.

    The repository qualifier is added by the tool; `query` carries only the
    repo-relative part of GitHub's search syntax.
    """
    operation: Literal["search_issues"] = Field(..., description="Operation to perform")
    query: str = Field(
        ...,
        description="Repo-relative GitHub search syntax, e.g. 'is:open label:bug memory leak'. "
                    "May not contain repo:, org:, or user: qualifiers.",
        min_length=1
    )
    sort: Optional[Literal["comments", "created", "updated"]] = Field(None, description="Sort field")
    order: Optional[Literal["asc", "desc"]] = Field("desc", description="Sort direction")
    include_pull_requests: Optional[bool] = Field(
        False, description="Search matches pull requests too; set true to keep them"
    )
    max_results: Optional[int] = Field(30, description="Maximum results to return", ge=1, le=100)
    page: Optional[int] = Field(
        None, description="Page to fetch; this operation reads exactly one page", ge=1
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "operation": "search_issues",
                "owner": "vital-ai",
                "repo": "vital-ai-sandbox",
                "query": "is:open label:bug",
                "max_results": 10
            }
        }
    }


# Union of every issue tool input model
GitHubIssueToolInput = Union[
    GitHubIssueListInput,
    GitHubIssueGetInput,
    GitHubIssueCreateInput,
    GitHubIssueUpdateInput,
    GitHubIssueCloseInput,
    GitHubIssueReopenInput,
    GitHubIssueCommentListInput,
    GitHubIssueCommentCreateInput,
    GitHubIssueCommentUpdateInput,
    GitHubIssueCommentDeleteInput,
    GitHubIssueAddLabelsInput,
    GitHubIssueRemoveLabelsInput,
    GitHubIssueAddAssigneesInput,
    GitHubIssueRemoveAssigneesInput,
    GitHubIssueSearchInput,
]

# operation string -> input model, used by the resolver in tool_request.py
GITHUB_ISSUE_OPERATION_MODELS = {
    "list_issues": GitHubIssueListInput,
    "get_issue": GitHubIssueGetInput,
    "create_issue": GitHubIssueCreateInput,
    "update_issue": GitHubIssueUpdateInput,
    "close_issue": GitHubIssueCloseInput,
    "reopen_issue": GitHubIssueReopenInput,
    "list_comments": GitHubIssueCommentListInput,
    "add_comment": GitHubIssueCommentCreateInput,
    "update_comment": GitHubIssueCommentUpdateInput,
    "delete_comment": GitHubIssueCommentDeleteInput,
    "add_labels": GitHubIssueAddLabelsInput,
    "remove_labels": GitHubIssueRemoveLabelsInput,
    "add_assignees": GitHubIssueAddAssigneesInput,
    "remove_assignees": GitHubIssueRemoveAssigneesInput,
    "search_issues": GitHubIssueSearchInput,
}


# ---------------------------------------------------------------------------
# Output models -- a flat projection of GitHub's verbose JSON, not a passthrough
# ---------------------------------------------------------------------------

class GitHubIssue(BaseModel):
    number: int = Field(..., description="Issue number")
    title: str = Field(..., description="Issue title")
    state: str = Field(..., description="open or closed")
    state_reason: Optional[str] = Field(None, description="Reason for the current state")
    body: Optional[str] = Field(None, description="Issue body, truncated if very long")
    body_truncated: bool = Field(False, description="True if the body was truncated")
    html_url: str = Field(..., description="Browser URL for the issue")
    user: Optional[str] = Field(None, description="Login of the issue author")
    assignees: List[str] = Field(default_factory=list, description="Logins of assignees")
    labels: List[str] = Field(default_factory=list, description="Label names")
    milestone: Optional[str] = Field(None, description="Milestone title")
    comments: int = Field(0, description="Number of comments")
    created_at: Optional[str] = Field(None, description="Creation timestamp")
    updated_at: Optional[str] = Field(None, description="Last update timestamp")
    closed_at: Optional[str] = Field(None, description="Close timestamp if closed")
    is_pull_request: bool = Field(False, description="True if this record is actually a pull request")


class GitHubComment(BaseModel):
    id: int = Field(..., description="Comment id")
    body: Optional[str] = Field(None, description="Comment body, truncated if very long")
    body_truncated: bool = Field(False, description="True if the body was truncated")
    user: Optional[str] = Field(None, description="Login of the comment author")
    html_url: Optional[str] = Field(None, description="Browser URL for the comment")
    created_at: Optional[str] = Field(None, description="Creation timestamp")
    updated_at: Optional[str] = Field(None, description="Last update timestamp")


class GitHubIssueToolOutput(GitHubOutputBase):
    """Output model for the GitHub issue tool"""
    tool: Literal["github_issue_tool"] = Field("github_issue_tool", description="Tool identifier")
    operation: str = Field(..., description="Operation that was performed")
    issues: List[GitHubIssue] = Field(default_factory=list, description="Issues from list/search operations")
    issue: Optional[GitHubIssue] = Field(None, description="Issue from single-issue operations")
    comments: List[GitHubComment] = Field(default_factory=list, description="Comments from list operations")
    comment: Optional[GitHubComment] = Field(None, description="Comment from single-comment operations")
    deleted_id: Optional[int] = Field(None, description="Id of a deleted resource")
    next_page: Optional[int] = Field(
        None,
        description="Page to request for the next batch, or null if there is no more. "
                    "Always use this rather than incrementing `page` yourself. For "
                    "list_comments and search_issues it is simply the next page. For "
                    "list_issues it may skip ahead (several pages can be consumed to "
                    "fill max_results after filtering out pull requests) or point back "
                    "at the page just read, when that page was only partly consumed -- "
                    "GitHub paginates by page with no offset, so resuming mid-page is "
                    "impossible and this errs toward repeating records rather than "
                    "skipping them. Deduplicate list_issues results by issue number."
    )
    total_count: Optional[int] = Field(
        None,
        description="Corpus total reported by GitHub for the query, set only where GitHub "
                    "supplies one (search). It counts records before this tool's own "
                    "filtering, so with include_pull_requests=false it can exceed "
                    "returned_count. For list operations GitHub gives no total and this "
                    "is null -- use returned_count."
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "tool": "github_issue_tool",
                "operation": "list_issues",
                "repository": "vital-ai/vital-ai-sandbox",
                "issues": [
                    {
                        "number": 1,
                        "title": "Investigate flaky test",
                        "state": "open",
                        "html_url": "https://github.com/vital-ai/vital-ai-sandbox/issues/1",
                        "user": "octocat",
                        "labels": ["bug"],
                        "comments": 0,
                        "is_pull_request": False
                    }
                ]
            }
        }
    }
