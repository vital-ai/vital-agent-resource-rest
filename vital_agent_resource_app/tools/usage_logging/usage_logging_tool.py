import json
from vital_agent_resource_app.tools.abstract_tool import AbstractTool
from vital_agent_resource_app.tools.tool_request import ToolRequest
from vital_agent_resource_app.tools.tool_response import ToolResponse
import requests


class UsageLoggingTool(AbstractTool):

    def handle_tool_request(self, tool_request: ToolRequest) -> ToolResponse:

        # handling logging of activity
        # used to capture agent activity in the API Gateway
        # for agent usage that is outside of the tool calls
        # such as internal actions of the agent that should be captured as billable usage

        request_data = tool_request.request_data

        tool_response = ToolResponse(data={})

        return tool_response

