
from pydantic import BaseModel, Field, model_validator
from typing import Optional, Union, List, Dict, Any, TYPE_CHECKING

# Direct imports to avoid forward reference issues
from vital_agent_resource_app.tools.google_address_validation.models import AddressValidationInput
from vital_agent_resource_app.tools.place_search.models import PlaceSearchInput
from vital_agent_resource_app.tools.weather.models import WeatherInput
from vital_agent_resource_app.tools.web_search.models import WebSearchInput
from vital_agent_resource_app.tools.serper_web_search.models import SerperWebSearchInput
from vital_agent_resource_app.tools.github.issue_models import (
    GitHubIssueToolInput, GITHUB_ISSUE_OPERATION_MODELS
)
from vital_agent_resource_app.tools.github.pr_models import (
    GitHubPRToolInput, GITHUB_PR_OPERATION_MODELS
)
from vital_agent_resource_app.tools.github.actions_models import (
    GitHubActionsToolInput, GITHUB_ACTIONS_OPERATION_MODELS
)
from vital_agent_resource_app.tools.github.repo_models import (
    GitHubRepoToolInput, GITHUB_REPO_OPERATION_MODELS
)
from vital_agent_resource_app.tools.send_email.models import EmailInput
from vital_agent_resource_app.tools.send_message.models import (
    LoopLookupSingleInput, LoopLookupBulkInput, LoopLookupStatusInput,
    LoopMessageSingleInput, LoopMessageGroupInput, LoopMessageAudioInput,
    LoopMessageReactionInput, LoopMessageStatusInput
)
from vital_agent_resource_app.tools.tool_name_enum import ToolName

# Type alias for tool input union
ToolInputType = Union[
    AddressValidationInput, 
    PlaceSearchInput, 
    WeatherInput,
    WebSearchInput,
    EmailInput,
    LoopLookupSingleInput,
    LoopLookupBulkInput,
    LoopLookupStatusInput,
    LoopMessageSingleInput,
    LoopMessageGroupInput,
    LoopMessageAudioInput,
    LoopMessageReactionInput,
    LoopMessageStatusInput,
    SerperWebSearchInput,
    GitHubIssueToolInput,
    GitHubPRToolInput,
    GitHubActionsToolInput,
    GitHubRepoToolInput
]

# Map tool names to their primary input model for disambiguation
_TOOL_INPUT_MODEL_MAP = {
    ToolName.google_address_validation_tool: AddressValidationInput,
    ToolName.place_search_tool: PlaceSearchInput,
    ToolName.weather_tool: WeatherInput,
    ToolName.google_web_search_tool: WebSearchInput,
    ToolName.serper_web_search_tool: SerperWebSearchInput,
    ToolName.send_email_tool: EmailInput,
    # Multi-operation tool: operation string -> input model
    ToolName.github_issue_tool: GITHUB_ISSUE_OPERATION_MODELS,
    ToolName.github_pr_tool: GITHUB_PR_OPERATION_MODELS,
    ToolName.github_actions_tool: GITHUB_ACTIONS_OPERATION_MODELS,
    ToolName.github_repo_tool: GITHUB_REPO_OPERATION_MODELS,
}

def _get_json_schema_extra(schema, model_type):
    """Generate examples dynamically from tool registry"""
    from vital_agent_resource_app.app import tool_registry
    examples = tool_registry.get_all_examples()
    schema['examples'] = examples


class ToolRequest(BaseModel):
    """Base tool request model with non-tool-specific parameters"""
    tool: ToolName = Field(..., description="Tool name to execute")
    request_id: Optional[str] = Field(None, description="Optional request identifier")
    timeout: Optional[int] = Field(None, description="Request timeout in seconds")
    tool_input: ToolInputType = Field(..., description="Tool-specific input parameters")

    @model_validator(mode='before')
    @classmethod
    def resolve_tool_input_model(cls, data: Any) -> Any:
        """Use the tool name to pick the correct input model when the Union is ambiguous."""
        if isinstance(data, dict):
            tool_name = data.get('tool')
            tool_input = data.get('tool_input')
            if tool_name and isinstance(tool_input, dict):
                try:
                    tool_enum = ToolName(tool_name)
                except ValueError:
                    return data
                model_cls = _TOOL_INPUT_MODEL_MAP.get(tool_enum)
                # Multi-operation tools map to {operation: Model} instead of a
                # single model; their input models overlap too much for the
                # Union to resolve on shape alone.
                if isinstance(model_cls, dict):
                    operation = tool_input.get('operation')
                    if operation not in model_cls:
                        # Falling through would produce one validation error per
                        # union member, which is unreadable. Name the problem.
                        raise ValueError(
                            f"Tool '{tool_name}' requires a valid 'operation' in tool_input. "
                            f"Got {operation!r}; expected one of: {', '.join(sorted(model_cls))}"
                        )
                    model_cls = model_cls[operation]
                if model_cls:
                    data['tool_input'] = model_cls(**tool_input)
        return data

    model_config = {
        "extra": "allow",
        "json_schema_extra": _get_json_schema_extra
    }
