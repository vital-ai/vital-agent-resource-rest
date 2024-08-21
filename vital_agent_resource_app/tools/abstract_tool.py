from abc import ABC, abstractmethod
from vital_agent_resource_app.tools.tool_request import ToolRequest
from vital_agent_resource_app.tools.tool_response import ToolResponse


class AbstractTool(ABC):

    @abstractmethod
    def handle_tool_request(self, tool_request: ToolRequest) -> ToolResponse:
        pass


