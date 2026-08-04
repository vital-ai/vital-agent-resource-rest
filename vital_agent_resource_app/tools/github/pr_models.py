from pydantic import BaseModel, Field
from typing import List, Optional, Literal, Union

from vital_agent_resource_app.tools.github.common_models import GitHubRepoBase, GitHubOutputBase


# ---------------------------------------------------------------------------
# Input models
# ---------------------------------------------------------------------------

class GitHubPRListInput(GitHubRepoBase):
    """List pull requests"""
    operation: Literal["list_prs"] = Field(..., description="Operation to perform")
    state: Optional[Literal["open", "closed", "all"]] = Field("open", description="PR state filter")
    head: Optional[str] = Field(None, description="Filter by head branch, as 'user:branch'")
    base: Optional[str] = Field(None, description="Filter by base branch name")
    sort: Optional[Literal["created", "updated", "popularity", "long-running"]] = Field(
        "created", description="Sort field"
    )
    direction: Optional[Literal["asc", "desc"]] = Field("desc", description="Sort direction")
    max_results: Optional[int] = Field(30, description="Maximum PRs to return", ge=1, le=100)
    page: Optional[int] = Field(None, description="Page number for pagination", ge=1)

    model_config = {
        "json_schema_extra": {
            "example": {
                "operation": "list_prs",
                "owner": "vital-ai",
                "repo": "vital-ai-sandbox",
                "state": "open"
            }
        }
    }


class GitHubPRGetInput(GitHubRepoBase):
    """Get a single pull request"""
    operation: Literal["get_pr"] = Field(..., description="Operation to perform")
    pr_number: int = Field(..., description="Pull request number", ge=1)


class GitHubPRCreateInput(GitHubRepoBase):
    """Open a new pull request"""
    operation: Literal["create_pr"] = Field(..., description="Operation to perform")
    title: str = Field(..., description="Pull request title", min_length=1)
    head: str = Field(..., description="Branch containing the changes", min_length=1)
    base: str = Field(..., description="Branch to merge into", min_length=1)
    body: Optional[str] = Field(None, description="Pull request description in Markdown")
    draft: Optional[bool] = Field(False, description="Open as a draft")
    maintainer_can_modify: Optional[bool] = Field(None, description="Allow maintainer edits")

    model_config = {
        "json_schema_extra": {
            "example": {
                "operation": "create_pr",
                "owner": "vital-ai",
                "repo": "vital-ai-sandbox",
                "title": "Fix flaky test",
                "head": "fix/flaky-test",
                "base": "main",
                "body": "Adds a retry around the list assertion."
            }
        }
    }


class GitHubPRUpdateInput(GitHubRepoBase):
    """Update a pull request. Only the fields provided are sent."""
    operation: Literal["update_pr"] = Field(..., description="Operation to perform")
    pr_number: int = Field(..., description="Pull request number", ge=1)
    title: Optional[str] = Field(None, description="New title", min_length=1)
    body: Optional[str] = Field(None, description="New description")
    state: Optional[Literal["open", "closed"]] = Field(None, description="New state")
    base: Optional[str] = Field(None, description="Retarget onto this base branch")


class GitHubPRFilesInput(GitHubRepoBase):
    """List the files a pull request touches"""
    operation: Literal["list_pr_files"] = Field(..., description="Operation to perform")
    pr_number: int = Field(..., description="Pull request number", ge=1)
    include_patch: Optional[bool] = Field(
        False,
        description="Include the diff hunk per file. Off by default -- patches are large "
                    "and blow up an agent's context."
    )
    max_results: Optional[int] = Field(50, description="Maximum files to return", ge=1, le=100)
    page: Optional[int] = Field(None, description="Page number for pagination", ge=1)


class GitHubPRCommentListInput(GitHubRepoBase):
    """List conversation comments on a pull request.

    These are issue comments. Review comments (anchored to a diff line) are a
    different API and are returned by list_pr_reviews / review endpoints.
    """
    operation: Literal["list_pr_comments"] = Field(..., description="Operation to perform")
    pr_number: int = Field(..., description="Pull request number", ge=1)
    max_results: Optional[int] = Field(30, description="Maximum comments to return", ge=1, le=100)
    page: Optional[int] = Field(None, description="Page number for pagination", ge=1)


class GitHubPRCommentCreateInput(GitHubRepoBase):
    """Add a conversation comment to a pull request"""
    operation: Literal["add_pr_comment"] = Field(..., description="Operation to perform")
    pr_number: int = Field(..., description="Pull request number", ge=1)
    body: str = Field(..., description="Comment body in Markdown", min_length=1)


class GitHubPRReviewListInput(GitHubRepoBase):
    """List reviews on a pull request"""
    operation: Literal["list_pr_reviews"] = Field(..., description="Operation to perform")
    pr_number: int = Field(..., description="Pull request number", ge=1)
    max_results: Optional[int] = Field(30, description="Maximum reviews to return", ge=1, le=100)


class GitHubPRReviewCreateInput(GitHubRepoBase):
    """Submit a review on a pull request.

    APPROVE is gated behind allow_pr_merge along with merge_pr, since an
    approving review can satisfy a branch protection rule and unblock a merge.
    """
    operation: Literal["create_pr_review"] = Field(..., description="Operation to perform")
    pr_number: int = Field(..., description="Pull request number", ge=1)
    event: Literal["APPROVE", "REQUEST_CHANGES", "COMMENT"] = Field(
        ..., description="Review verdict"
    )
    body: Optional[str] = Field(None, description="Review body; required for REQUEST_CHANGES and COMMENT")


class GitHubPRMergeInput(GitHubRepoBase):
    """Merge a pull request. Gated behind allow_pr_merge, off by default."""
    operation: Literal["merge_pr"] = Field(..., description="Operation to perform")
    pr_number: int = Field(..., description="Pull request number", ge=1)
    merge_method: Optional[Literal["merge", "squash", "rebase"]] = Field(
        "merge", description="How to merge"
    )
    commit_title: Optional[str] = Field(None, description="Title for the merge commit")
    commit_message: Optional[str] = Field(None, description="Body for the merge commit")
    sha: Optional[str] = Field(
        None, description="Head SHA the merge must match; guards against merging newer commits"
    )


GitHubPRToolInput = Union[
    GitHubPRListInput,
    GitHubPRGetInput,
    GitHubPRCreateInput,
    GitHubPRUpdateInput,
    GitHubPRFilesInput,
    GitHubPRCommentListInput,
    GitHubPRCommentCreateInput,
    GitHubPRReviewListInput,
    GitHubPRReviewCreateInput,
    GitHubPRMergeInput,
]

GITHUB_PR_OPERATION_MODELS = {
    "list_prs": GitHubPRListInput,
    "get_pr": GitHubPRGetInput,
    "create_pr": GitHubPRCreateInput,
    "update_pr": GitHubPRUpdateInput,
    "list_pr_files": GitHubPRFilesInput,
    "list_pr_comments": GitHubPRCommentListInput,
    "add_pr_comment": GitHubPRCommentCreateInput,
    "list_pr_reviews": GitHubPRReviewListInput,
    "create_pr_review": GitHubPRReviewCreateInput,
    "merge_pr": GitHubPRMergeInput,
}


# ---------------------------------------------------------------------------
# Output models
# ---------------------------------------------------------------------------

class GitHubPullRequest(BaseModel):
    number: int = Field(..., description="Pull request number")
    title: str = Field(..., description="Pull request title")
    state: str = Field(..., description="open or closed")
    draft: bool = Field(False, description="True if the PR is a draft")
    body: Optional[str] = Field(None, description="Description, truncated if very long")
    body_truncated: bool = Field(False, description="True if the body was truncated")
    html_url: str = Field(..., description="Browser URL")
    user: Optional[str] = Field(None, description="Login of the PR author")
    head: Optional[str] = Field(None, description="Head branch name")
    base: Optional[str] = Field(None, description="Base branch name")
    head_sha: Optional[str] = Field(None, description="Head commit SHA")
    merged: bool = Field(False, description="True if the PR has been merged")
    mergeable: Optional[bool] = Field(None, description="GitHub's mergeability verdict, if computed")
    mergeable_state: Optional[str] = Field(None, description="clean, blocked, dirty, unknown, ...")
    merged_at: Optional[str] = Field(None, description="Merge timestamp")
    labels: List[str] = Field(default_factory=list, description="Label names")
    assignees: List[str] = Field(default_factory=list, description="Logins of assignees")
    requested_reviewers: List[str] = Field(default_factory=list, description="Logins asked to review")
    comments: Optional[int] = Field(None, description="Conversation comment count")
    review_comments: Optional[int] = Field(None, description="Review comment count")
    commits: Optional[int] = Field(None, description="Number of commits")
    additions: Optional[int] = Field(None, description="Lines added")
    deletions: Optional[int] = Field(None, description="Lines removed")
    changed_files: Optional[int] = Field(None, description="Number of files changed")
    created_at: Optional[str] = Field(None, description="Creation timestamp")
    updated_at: Optional[str] = Field(None, description="Last update timestamp")
    closed_at: Optional[str] = Field(None, description="Close timestamp")


class GitHubPRFile(BaseModel):
    filename: str = Field(..., description="Path of the changed file")
    status: Optional[str] = Field(None, description="added, modified, removed, renamed, ...")
    additions: int = Field(0, description="Lines added")
    deletions: int = Field(0, description="Lines removed")
    changes: int = Field(0, description="Total line changes")
    previous_filename: Optional[str] = Field(None, description="Prior path for renames")
    patch: Optional[str] = Field(None, description="Diff hunk, only when include_patch is set")
    patch_truncated: bool = Field(False, description="True if the patch was truncated")


class GitHubPRReview(BaseModel):
    id: int = Field(..., description="Review id")
    user: Optional[str] = Field(None, description="Login of the reviewer")
    state: Optional[str] = Field(None, description="APPROVED, CHANGES_REQUESTED, COMMENTED, ...")
    body: Optional[str] = Field(None, description="Review body, truncated if very long")
    body_truncated: bool = Field(False, description="True if the body was truncated")
    html_url: Optional[str] = Field(None, description="Browser URL")
    submitted_at: Optional[str] = Field(None, description="Submission timestamp")


class GitHubPRComment(BaseModel):
    id: int = Field(..., description="Comment id")
    body: Optional[str] = Field(None, description="Comment body, truncated if very long")
    body_truncated: bool = Field(False, description="True if the body was truncated")
    user: Optional[str] = Field(None, description="Login of the comment author")
    html_url: Optional[str] = Field(None, description="Browser URL")
    created_at: Optional[str] = Field(None, description="Creation timestamp")
    updated_at: Optional[str] = Field(None, description="Last update timestamp")


class GitHubPRMergeResult(BaseModel):
    merged: bool = Field(..., description="Whether the merge succeeded")
    sha: Optional[str] = Field(None, description="SHA of the merge commit")
    message: Optional[str] = Field(None, description="Message returned by GitHub")


class GitHubPRToolOutput(GitHubOutputBase):
    """Output model for the GitHub pull request tool"""
    tool: Literal["github_pr_tool"] = Field("github_pr_tool", description="Tool identifier")
    operation: str = Field(..., description="Operation that was performed")
    pull_requests: List[GitHubPullRequest] = Field(default_factory=list, description="PRs from list operations")
    pull_request: Optional[GitHubPullRequest] = Field(None, description="PR from single-PR operations")
    files: List[GitHubPRFile] = Field(default_factory=list, description="Changed files")
    reviews: List[GitHubPRReview] = Field(default_factory=list, description="Reviews")
    review: Optional[GitHubPRReview] = Field(None, description="Newly created review")
    comments: List[GitHubPRComment] = Field(default_factory=list, description="Conversation comments")
    comment: Optional[GitHubPRComment] = Field(None, description="Newly created comment")
    merge_result: Optional[GitHubPRMergeResult] = Field(None, description="Outcome of a merge")
    next_page: Optional[int] = Field(
        None,
        description="Page to request for the next batch, or null if there is no more. "
                    "Every list operation on this tool reads exactly one page, so this "
                    "is the next page and results never repeat."
    )
    total_count: Optional[int] = Field(
        None,
        description="Corpus total reported by GitHub, set only where GitHub supplies one. "
                    "GitHub gives no total for pull request list endpoints, so this is "
                    "normally null -- use returned_count."
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "tool": "github_pr_tool",
                "operation": "list_prs",
                "repository": "vital-ai/vital-ai-sandbox",
                "pull_requests": [
                    {
                        "number": 1,
                        "title": "Fix flaky test",
                        "state": "open",
                        "draft": False,
                        "html_url": "https://github.com/vital-ai/vital-ai-sandbox/pull/1",
                        "head": "fix/flaky-test",
                        "base": "main",
                        "merged": False
                    }
                ]
            }
        }
    }
