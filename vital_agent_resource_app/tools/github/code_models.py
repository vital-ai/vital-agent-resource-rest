from pydantic import BaseModel, Field
from typing import List, Optional, Literal, Union

from vital_agent_resource_app.tools.github.common_models import GitHubRepoBase, GitHubOutputBase
from vital_agent_resource_app.tools.github.repo_models import GitHubBranch


# ---------------------------------------------------------------------------
# Input models
#
# This tool exists to separate authority from resource. Every operation here
# changes repository code -- a branch ref, a commit, or a merge landing commits
# on a branch. They were previously split across github_repo_tool and
# github_pr_tool by GitHub resource, which meant an agent registered to *read*
# code necessarily had the write operations in its schema, gated only by a
# service-wide config flag. Config gates are per deployment; tool registration
# is per agent, so a tool has to be a single authority for registration to be a
# usable control.
# ---------------------------------------------------------------------------

class GitHubCreateBranchInput(GitHubRepoBase):
    """Create a branch.

    Creates a ref pointing at an existing commit, so it changes no file content
    and is gated by allow_writes rather than allow_content_writes. It lives in
    this tool anyway: it exists only to carry code changes, and separating it
    from the write it precedes would defeat the point of the split.

    This is the operation that makes create_pr reachable.
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

class GitHubMergeInput(GitHubRepoBase):
    """Merge a pull request. Gated behind allow_pr_merge, off by default.

    Merging lands commits on the base branch, which is a code change -- which is
    why it sits here rather than with the pull request metadata operations.
    """
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

GitHubCodeToolInput = Union[
    GitHubCreateBranchInput,
    GitHubWriteFileInput,
    GitHubMergeInput,
]

GITHUB_CODE_OPERATION_MODELS = {
    "create_branch": GitHubCreateBranchInput,
    "create_or_update_file": GitHubWriteFileInput,
    "merge_pr": GitHubMergeInput,
}


# ---------------------------------------------------------------------------
# Output models
# ---------------------------------------------------------------------------

class GitHubWriteResult(BaseModel):
    path: str = Field(..., description="Path written")
    branch: str = Field(..., description="Branch committed to")
    commit_sha: Optional[str] = Field(None, description="SHA of the resulting commit")
    blob_sha: Optional[str] = Field(None, description="SHA of the written blob")
    created: bool = Field(..., description="True if the file was created, false if updated")
    html_url: Optional[str] = Field(None, description="Browser URL for the commit")

class GitHubMergeResult(BaseModel):
    merged: bool = Field(..., description="Whether the merge succeeded")
    sha: Optional[str] = Field(None, description="SHA of the merge commit")
    message: Optional[str] = Field(None, description="Message returned by GitHub")

class GitHubCodeToolOutput(GitHubOutputBase):
    """Output model for the GitHub code tool"""
    tool: Literal["github_code_tool"] = Field("github_code_tool", description="Tool identifier")
    operation: str = Field(..., description="Operation that was performed")
    branch: Optional[GitHubBranch] = Field(None, description="Newly created branch")
    write_result: Optional[GitHubWriteResult] = Field(
        None, description="Outcome of a content write")
    merge_result: Optional[GitHubMergeResult] = Field(
        None, description="Outcome of a merge")

    model_config = {
        "json_schema_extra": {
            "example": {
                "tool": "github_code_tool",
                "operation": "create_branch",
                "repository": "vital-ai/vital-ai-sandbox",
                "branch": {"name": "fix/flaky-test", "sha": "abc123", "is_default": False}
            }
        }
    }
