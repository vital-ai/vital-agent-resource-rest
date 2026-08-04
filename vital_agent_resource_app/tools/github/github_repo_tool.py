import logging
import time
from typing import Any, Dict, List, Optional

from vital_agent_resource_app.tools.abstract_tool import AbstractTool
from vital_agent_resource_app.tools.tool_request import ToolRequest
from vital_agent_resource_app.tools.tool_response import ToolResponse
from vital_agent_resource_app.tools.github.github_client import (
    GitHubClient, GitHubToolError, rate_limit_remaining
)
from vital_agent_resource_app.tools.github.repo_models import (
    GitHubRepoGetInput, GitHubRepository, GitHubRepoToolOutput
)

logger = logging.getLogger("VitalAgentContainerLogger")


class GitHubRepoTool(AbstractTool):
    """Repository metadata.

    Read-only. This is also where contents and refs operations belong if they
    are ever added, which is why get_repo lives here rather than being bolted
    onto the issue tool.
    """

    def __init__(self, config: dict, client: GitHubClient):
        super().__init__(config or {})
        self.client = client
        self._dispatch = {
            GitHubRepoGetInput: self._get_repo,
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

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

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
        logger.info(f"Rate limit remaining: {output.rate_limit_remaining}")
        logger.info("=" * 80)
