from pydantic import BaseModel, Field
from typing import List, Optional, Literal, Union

from vital_agent_resource_app.tools.github.common_models import GitHubRepoBase, GitHubOutputBase


# ---------------------------------------------------------------------------
# Input models
# ---------------------------------------------------------------------------

class GitHubRepoGetInput(GitHubRepoBase):
    """Get repository metadata.

    Chiefly here so an agent can learn the default branch rather than guessing
    it -- `main` is a guess, and wrong on older repositories. Also supplies
    open_issues_count natively, which otherwise has to be reconstructed from a
    search.
    """
    operation: Literal["get_repo"] = Field(..., description="Operation to perform")

    model_config = {
        "json_schema_extra": {
            "example": {
                "operation": "get_repo",
                "owner": "vital-ai",
                "repo": "vital-ai-sandbox"
            }
        }
    }


class GitHubGetFileInput(GitHubRepoBase):
    """Read a file, or list a directory, from the repository."""
    operation: Literal["get_file_contents"] = Field(..., description="Operation to perform")
    path: str = Field(..., description="Path within the repository", min_length=1)
    ref: Optional[str] = Field(
        None, description="Branch, tag or commit SHA. Defaults to the default branch.")
    max_chars: Optional[int] = Field(
        20000, description="Truncate file content beyond this many characters",
        ge=100, le=200000)


class GitHubListBranchesInput(GitHubRepoBase):
    """List branches"""
    operation: Literal["list_branches"] = Field(..., description="Operation to perform")
    protected_only: Optional[bool] = Field(None, description="Only protected branches")
    max_results: Optional[int] = Field(50, description="Maximum branches to return", ge=1, le=100)
    page: Optional[int] = Field(
        None, description="Page to fetch; this operation reads exactly one page", ge=1)


class GitHubListCommitsInput(GitHubRepoBase):
    """List commits"""
    operation: Literal["list_commits"] = Field(..., description="Operation to perform")
    ref: Optional[str] = Field(None, description="Branch, tag or SHA to list from")
    path: Optional[str] = Field(None, description="Only commits touching this path")
    author: Optional[str] = Field(None, description="Filter by author login or email")
    since: Optional[str] = Field(None, description="Only commits after this ISO 8601 timestamp")
    until: Optional[str] = Field(None, description="Only commits before this ISO 8601 timestamp")
    max_results: Optional[int] = Field(30, description="Maximum commits to return", ge=1, le=100)
    page: Optional[int] = Field(
        None, description="Page to fetch; this operation reads exactly one page", ge=1)


class GitHubCompareRefsInput(GitHubRepoBase):
    """Compare two refs -- what changed between them"""
    operation: Literal["compare_refs"] = Field(..., description="Operation to perform")
    base: str = Field(..., description="Base ref (branch, tag or SHA)", min_length=1)
    head: str = Field(..., description="Head ref (branch, tag or SHA)", min_length=1)
    include_patch: Optional[bool] = Field(
        False, description="Include diff hunks per file. Off by default -- patches are large.")
    max_files: Optional[int] = Field(50, description="Maximum changed files to return", ge=1, le=100)


class GitHubCreateBranchInput(GitHubRepoBase):
    """Create a branch.

    Creates a ref pointing at an existing commit; it does not change any file, so
    it is gated by allow_writes rather than allow_content_writes. This is the
    operation that makes create_pr reachable.
    """
    operation: Literal["create_branch"] = Field(..., description="Operation to perform")
    branch: str = Field(..., description="New branch name", min_length=1)
    from_ref: Optional[str] = Field(
        None, description="Branch or SHA to branch from. Defaults to the default branch.")


class GitHubWriteFileInput(GitHubRepoBase):
    """Create or update a file, committing the change.

    Gated by allow_content_writes (default off) -- this is the only operation in
    the service that writes repository content, which is a different authority
    from filing an issue.

    `branch` is required rather than defaulting: GitHub would otherwise commit to
    the default branch, and an omitted field should not be the path to writing on
    main. Writing to the default branch additionally requires
    allow_default_branch_writes, so the normal flow is create_branch -> write ->
    create_pr.
    """
    operation: Literal["create_or_update_file"] = Field(..., description="Operation to perform")
    path: str = Field(..., description="Path within the repository", min_length=1)
    content: str = Field(..., description="Full file content as text (not base64)")
    message: str = Field(..., description="Commit message", min_length=1)
    branch: str = Field(..., description="Branch to commit on", min_length=1)
    sha: Optional[str] = Field(
        None,
        description="Blob SHA of the file being replaced. Required by GitHub when "
                    "updating an existing file; the tool looks it up if omitted.")


GitHubRepoToolInput = Union[
    GitHubRepoGetInput,
    GitHubGetFileInput,
    GitHubListBranchesInput,
    GitHubListCommitsInput,
    GitHubCompareRefsInput,
    GitHubCreateBranchInput,
    GitHubWriteFileInput,
]

GITHUB_REPO_OPERATION_MODELS = {
    "get_repo": GitHubRepoGetInput,
    "get_file_contents": GitHubGetFileInput,
    "list_branches": GitHubListBranchesInput,
    "list_commits": GitHubListCommitsInput,
    "compare_refs": GitHubCompareRefsInput,
    "create_branch": GitHubCreateBranchInput,
    "create_or_update_file": GitHubWriteFileInput,
}


# ---------------------------------------------------------------------------
# Output models
# ---------------------------------------------------------------------------

class GitHubRepository(BaseModel):
    full_name: str = Field(..., description="owner/repo")
    name: Optional[str] = Field(None, description="Repository name")
    owner: Optional[str] = Field(None, description="Owner login")
    private: Optional[bool] = Field(None, description="True if the repository is private")
    description: Optional[str] = Field(None, description="Repository description")
    default_branch: Optional[str] = Field(
        None, description="Default branch -- use this as `base` when opening a pull request")
    html_url: Optional[str] = Field(None, description="Browser URL")
    language: Optional[str] = Field(None, description="Primary language")
    topics: List[str] = Field(default_factory=list, description="Repository topics")
    open_issues_count: Optional[int] = Field(
        None,
        description="GitHub's open issue count. Note this includes open pull requests, "
                    "since GitHub counts pull requests as issues.")
    archived: Optional[bool] = Field(None, description="True if the repository is archived")
    disabled: Optional[bool] = Field(None, description="True if the repository is disabled")
    has_issues: Optional[bool] = Field(None, description="True if the issue tracker is enabled")
    created_at: Optional[str] = Field(None, description="Creation timestamp")
    updated_at: Optional[str] = Field(None, description="Last update timestamp")
    pushed_at: Optional[str] = Field(None, description="Last push timestamp")


class GitHubFileContent(BaseModel):
    path: str = Field(..., description="Path within the repository")
    type: Optional[str] = Field(None, description="file, dir, symlink or submodule")
    size: Optional[int] = Field(None, description="Size in bytes")
    sha: Optional[str] = Field(None, description="Blob SHA -- pass to create_or_update_file")
    content: Optional[str] = Field(
        None, description="Decoded text content. Null for binary files and directories.")
    content_truncated: bool = Field(False, description="True if content was truncated")
    is_binary: bool = Field(False, description="True if the file could not be decoded as text")
    html_url: Optional[str] = Field(None, description="Browser URL")
    entries: List[str] = Field(
        default_factory=list, description="Directory entries, when path is a directory")


class GitHubBranch(BaseModel):
    name: str = Field(..., description="Branch name")
    sha: Optional[str] = Field(None, description="Commit the branch points at")
    protected: Optional[bool] = Field(None, description="True if the branch is protected")
    is_default: bool = Field(False, description="True if this is the repository default branch")


class GitHubCommit(BaseModel):
    sha: str = Field(..., description="Commit SHA")
    message: Optional[str] = Field(None, description="Commit message, first line onwards")
    author: Optional[str] = Field(None, description="Author login, or name if no account")
    date: Optional[str] = Field(None, description="Author date")
    html_url: Optional[str] = Field(None, description="Browser URL")


class GitHubComparison(BaseModel):
    status: Optional[str] = Field(None, description="ahead, behind, identical or diverged")
    ahead_by: Optional[int] = Field(None, description="Commits head is ahead of base")
    behind_by: Optional[int] = Field(None, description="Commits head is behind base")
    total_commits: Optional[int] = Field(None, description="Commits in the comparison")
    files_changed: Optional[int] = Field(None, description="Number of files changed")


class GitHubWriteResult(BaseModel):
    path: str = Field(..., description="Path written")
    branch: str = Field(..., description="Branch committed to")
    commit_sha: Optional[str] = Field(None, description="SHA of the resulting commit")
    blob_sha: Optional[str] = Field(None, description="SHA of the written blob")
    created: bool = Field(..., description="True if the file was created, false if updated")
    html_url: Optional[str] = Field(None, description="Browser URL for the commit")


class GitHubRepoToolOutput(GitHubOutputBase):
    """Output model for the GitHub repository tool"""
    tool: Literal["github_repo_tool"] = Field("github_repo_tool", description="Tool identifier")
    operation: str = Field(..., description="Operation that was performed")
    repository_info: Optional[GitHubRepository] = Field(
        None, description="Repository metadata")
    file: Optional[GitHubFileContent] = Field(None, description="File or directory contents")
    branches: List[GitHubBranch] = Field(default_factory=list, description="Branches")
    branch: Optional[GitHubBranch] = Field(None, description="Newly created branch")
    commits: List[GitHubCommit] = Field(default_factory=list, description="Commits")
    comparison: Optional[GitHubComparison] = Field(None, description="Ref comparison summary")
    files: List[dict] = Field(
        default_factory=list, description="Changed files from compare_refs")
    write_result: Optional[GitHubWriteResult] = Field(
        None, description="Outcome of a content write")

    model_config = {
        "json_schema_extra": {
            "example": {
                "tool": "github_repo_tool",
                "operation": "get_repo",
                "repository": "vital-ai/vital-ai-sandbox",
                "repository_info": {
                    "full_name": "vital-ai/vital-ai-sandbox",
                    "private": True,
                    "default_branch": "main",
                    "has_issues": True,
                    "open_issues_count": 0
                }
            }
        }
    }
