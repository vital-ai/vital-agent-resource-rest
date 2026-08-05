from pydantic import BaseModel, Field, model_validator
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

class GitHubDeleteBranchInput(GitHubRepoBase):
    """Delete a branch.

    The counterpart to create_branch. Without it every branch an agent creates
    is permanent, which makes automated fixtures accumulate refs forever.

    Refuses the default branch outright -- not gated, refused: there is no
    legitimate reason for an agent to delete it, and no config flag should make
    it possible.
    """
    operation: Literal["delete_branch"] = Field(..., description="Operation to perform")
    branch: str = Field(..., description="Branch to delete", min_length=1)


class GitHubDeleteFileInput(GitHubRepoBase):
    """Delete a file, committing the removal.

    The counterpart to create_or_update_file, and gated the same way. Without it
    an agent can add and modify but never remove -- including its own mistakes.
    """
    operation: Literal["delete_file"] = Field(..., description="Operation to perform")
    path: str = Field(..., description="Path within the repository", min_length=1)
    message: str = Field(..., description="Commit message", min_length=1)
    branch: str = Field(..., description="Branch to commit on", min_length=1)
    sha: Optional[str] = Field(
        None,
        description="Blob SHA of the file being deleted. Required by GitHub; the tool "
                    "looks it up if omitted.")


class GitHubFileWrite(BaseModel):
    """One file in a multi-file commit."""
    path: str = Field(..., description="Repository-relative path", min_length=1)
    content: str = Field(..., description="Full file content as text (not base64)")


class GitHubWriteFilesInput(GitHubRepoBase):
    """Create, update and/or delete several files in ONE commit, via the Git Data API.

    The multi-file counterpart to create_or_update_file. Use it when a change is
    only correct as a unit -- code plus the test that proves it, or an add plus
    the delete that makes it a move. Sequential single-file writes cannot express
    that: a failure part-way through leaves the branch half-applied, in a state
    no record describes.
    """
    operation: Literal["write_files"] = Field(..., description="Operation to perform")
    branch: str = Field(..., description="Branch to commit on", min_length=1)
    message: str = Field(..., description="Commit message", min_length=1)
    files: List[GitHubFileWrite] = Field(
        default_factory=list, description="Files to create or overwrite")
    deletions: List[str] = Field(
        default_factory=list,
        description="Repository-relative paths to remove in the same commit")
    from_ref: Optional[str] = Field(
        None,
        description="Base the commit on this ref instead of the branch's current head. "
                    "Setting it makes the result a function of the inputs alone -- the "
                    "branch becomes base + this tree -- so re-running yields the same "
                    "single-commit diff rather than stacking a commit per attempt. "
                    "Requires force=true, because it is a non-fast-forward update.")
    force: bool = Field(
        False,
        description="Allow a non-fast-forward branch update, discarding commits the branch "
                    "had. Required with from_ref. Explicit rather than implied: this is how "
                    "the idempotent re-run property is achieved and also how history is "
                    "lost, so it should never be a side effect of an omitted field.")

    @model_validator(mode='after')
    def check_payload(self):
        if not self.files and not self.deletions:
            # An empty commit is indistinguishable from a bug that computed no
            # changes, so refuse rather than record one.
            raise ValueError(
                "write_files needs at least one entry in `files` or `deletions`; "
                "an empty commit would hide a caller that computed no changes."
            )
        if self.from_ref and not self.force:
            raise ValueError(
                "from_ref rewrites the branch to base + this tree, which is a "
                "non-fast-forward update. Set force=true to confirm."
            )
        paths = [f.path for f in self.files]
        overlap = sorted(set(paths) & set(self.deletions))
        if overlap:
            raise ValueError(
                f"{overlap} appear in both `files` and `deletions`; the commit would "
                f"both write and remove them."
            )
        duplicates = sorted({p for p in paths if paths.count(p) > 1})
        if duplicates:
            raise ValueError(f"duplicate paths in `files`: {duplicates}")
        return self


GitHubCodeToolInput = Union[
    GitHubCreateBranchInput,
    GitHubWriteFileInput,
    GitHubMergeInput,
    GitHubDeleteBranchInput,
    GitHubDeleteFileInput,
    GitHubWriteFilesInput,
]

GITHUB_CODE_OPERATION_MODELS = {
    "create_branch": GitHubCreateBranchInput,
    "create_or_update_file": GitHubWriteFileInput,
    "merge_pr": GitHubMergeInput,
    "delete_branch": GitHubDeleteBranchInput,
    "delete_file": GitHubDeleteFileInput,
    "write_files": GitHubWriteFilesInput,
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

class GitHubDeleteResult(BaseModel):
    target: str = Field(..., description="What was deleted -- a branch name or a file path")
    kind: str = Field(..., description="branch or file")
    branch: Optional[str] = Field(None, description="Branch the deletion was committed on")
    commit_sha: Optional[str] = Field(None, description="Commit recording a file deletion")


class GitHubCommitResult(BaseModel):
    branch: str = Field(..., description="Branch the commit landed on")
    commit_sha: Optional[str] = Field(None, description="SHA of the new commit")
    tree_sha: Optional[str] = Field(None, description="SHA of the new tree")
    parent_sha: Optional[str] = Field(None, description="Commit this was based on")
    written: List[str] = Field(default_factory=list, description="Paths created or updated")
    deleted: List[str] = Field(default_factory=list, description="Paths removed")
    branch_created: bool = Field(False, description="True if the branch did not exist")
    forced: bool = Field(False, description="True if the ref was force-updated")
    html_url: Optional[str] = Field(None, description="Browser URL for the commit")


class GitHubCodeToolOutput(GitHubOutputBase):
    """Output model for the GitHub code tool"""
    tool: Literal["github_code_tool"] = Field("github_code_tool", description="Tool identifier")
    operation: str = Field(..., description="Operation that was performed")
    branch: Optional[GitHubBranch] = Field(None, description="Newly created branch")
    write_result: Optional[GitHubWriteResult] = Field(
        None, description="Outcome of a content write")
    merge_result: Optional[GitHubMergeResult] = Field(
        None, description="Outcome of a merge")
    delete_result: Optional[GitHubDeleteResult] = Field(
        None, description="Outcome of a branch or file deletion")
    commit_result: Optional[GitHubCommitResult] = Field(
        None, description="Outcome of a multi-file commit")

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
