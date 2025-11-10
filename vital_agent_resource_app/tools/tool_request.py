
from pydantic import BaseModel, Field
from typing import Optional, Union, List, Dict, Any, TYPE_CHECKING

# Direct imports to avoid forward reference issues
from vital_agent_resource_app.tools.google_address_validation.models import AddressValidationInput
from vital_agent_resource_app.tools.place_search.models import PlaceSearchInput
from vital_agent_resource_app.tools.weather.models import WeatherInput
from vital_agent_resource_app.tools.web_search.models import WebSearchInput
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
    LoopMessageStatusInput
]

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

    model_config = {
        "extra": "allow",
        "json_schema_extra": _get_json_schema_extra
    }
