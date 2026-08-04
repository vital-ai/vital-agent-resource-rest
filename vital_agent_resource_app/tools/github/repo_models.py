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


GitHubRepoToolInput = Union[GitHubRepoGetInput]

GITHUB_REPO_OPERATION_MODELS = {
    "get_repo": GitHubRepoGetInput,
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


class GitHubRepoToolOutput(GitHubOutputBase):
    """Output model for the GitHub repository tool"""
    tool: Literal["github_repo_tool"] = Field("github_repo_tool", description="Tool identifier")
    operation: str = Field(..., description="Operation that was performed")
    repository_info: Optional[GitHubRepository] = Field(
        None, description="Repository metadata")

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
