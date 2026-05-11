
from pydantic import BaseModel, Field, model_validator
from typing import Optional, Union, List, Dict, Any, TYPE_CHECKING

# Direct imports to avoid forward reference issues
from vital_agent_resource_app.tools.google_address_validation.models import AddressValidationInput
from vital_agent_resource_app.tools.place_search.models import PlaceSearchInput
from vital_agent_resource_app.tools.weather.models import WeatherInput
from vital_agent_resource_app.tools.web_search.models import WebSearchInput
from vital_agent_resource_app.tools.serper_web_search.models import SerperWebSearchInput
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
    SerperWebSearchInput
]

# Map tool names to their primary input model for disambiguation
_TOOL_INPUT_MODEL_MAP = {
    ToolName.google_address_validation_tool: AddressValidationInput,
    ToolName.place_search_tool: PlaceSearchInput,
    ToolName.weather_tool: WeatherInput,
    ToolName.google_web_search_tool: WebSearchInput,
    ToolName.serper_web_search_tool: SerperWebSearchInput,
    ToolName.send_email_tool: EmailInput,
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
                if model_cls:
                    data['tool_input'] = model_cls(**tool_input)
        return data

    model_config = {
        "extra": "allow",
        "json_schema_extra": _get_json_schema_extra
    }
