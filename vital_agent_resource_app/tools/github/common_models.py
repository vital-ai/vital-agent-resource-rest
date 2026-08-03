from pydantic import BaseModel, Field
from typing import Optional


class GitHubRepoBase(BaseModel):
    """Base for every GitHub tool input.

    owner/repo are required on every request -- there are no config defaults, so
    the caller always names the target repository explicitly and the allowlist
    check in GitHubClient has something to check.
    """
    owner: str = Field(..., description="Repository owner (user or organization)", min_length=1)
    repo: str = Field(..., description="Repository name", min_length=1)


class GitHubOutputBase(BaseModel):
    """Fields shared by every GitHub tool output."""
    repository: Optional[str] = Field(None, description="Repository the operation targeted, as 'owner/repo'")
    truncated: bool = Field(False, description="True if more results existed than were returned")
    api_error: Optional[str] = Field(None, description="Error message if the GitHub API call failed")
    api_status_code: Optional[int] = Field(None, description="GitHub API status code if the call failed")
    rate_limit_remaining: Optional[int] = Field(None, description="Requests remaining in the current rate limit window")
