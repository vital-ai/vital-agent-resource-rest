from abc import ABC, abstractmethod
from vital_agent_resource_app.tools.tool_request import ToolRequest
from vital_agent_resource_app.tools.tool_response import ToolResponse
from typing import List, Dict, Any
import time


class AbstractTool(ABC):

    def __init__(self, config: dict):
        self.config = config

    @abstractmethod
    def handle_tool_request(self, tool_request: ToolRequest) -> ToolResponse:
        pass

    @abstractmethod
    def get_examples(self) -> List[Dict[str, Any]]:
        """Return list of example requests for this tool"""
        pass

    def _create_success_response(self, tool_output: dict, start_time: float = None) -> ToolResponse:
        """Helper method to create successful tool response"""
        duration_ms = int((time.time() - (start_time or time.time())) * 1000) if start_time else 0
        return ToolResponse.create_success(tool_output, duration_ms)

    def _create_error_response(self, error_message: str, start_time: float = None) -> ToolResponse:
        """Helper method to create error tool response"""
        duration_ms = int((time.time() - (start_time or time.time())) * 1000) if start_time else 0
        return ToolResponse.create_error(error_message, duration_ms)

