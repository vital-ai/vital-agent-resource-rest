from pydantic import BaseModel, Field
from typing import Optional, Union
import time

# Direct imports to avoid forward reference issues
from vital_agent_resource_app.tools.google_address_validation.models import AddressValidationOutput
from vital_agent_resource_app.tools.place_search.models import PlaceSearchOutput
from vital_agent_resource_app.tools.weather.models import WeatherOutput
from vital_agent_resource_app.tools.web_search.models import WebSearchOutput
from vital_agent_resource_app.tools.serper_web_search.models import SerperWebSearchOutput
from vital_agent_resource_app.tools.send_email.models import EmailOutput


class ToolResponse(BaseModel):
    """Base tool response model with non-tool-specific fields"""
    duration_ms: Optional[int] = Field(None, description="Response duration in milliseconds")
    success: bool = Field(..., description="Whether the tool execution was successful")
    error_message: Optional[str] = Field(None, description="Error message if execution failed")
    tool_output: Optional[Union[
        AddressValidationOutput, 
        PlaceSearchOutput, 
        WeatherOutput,
        WebSearchOutput,
        SerperWebSearchOutput,
        EmailOutput,
        dict
        ]] = Field(None, description="Tool-specific output data")

    def to_dict(self):
        d = self.dict()
        if d.get('tool_output') is None:
            d['tool_output'] = {"results": []}
        elif isinstance(d.get('tool_output'), dict) and 'results' not in d['tool_output']:
            d['tool_output']['results'] = []
        return d

    @classmethod
    def create_success(cls, tool_output, duration_ms: int):
        """Create a successful tool response"""
        return cls(
            duration_ms=duration_ms,
            success=True,
            tool_output=tool_output
        )

    @classmethod
    def create_error(cls, error_message: str, duration_ms: int):
        """Create an error tool response"""
        return cls(
            duration_ms=duration_ms,
            success=False,
            error_message=error_message,
            tool_output=None
        )

