from vital_agent_resource_app.tools.abstract_tool import AbstractTool
from vital_agent_resource_app.tools.tool_request import ToolRequest
from vital_agent_resource_app.tools.tool_response import ToolResponse
import requests
from serpapi import GoogleSearch

class GoogleWebSearchTool(AbstractTool):

    def handle_tool_request(self, tool_request: ToolRequest) -> ToolResponse:

        request_data = tool_request.request_data

        tool_response = self.google_web_search()

        return tool_response


    def google_web_search(self):

        api_key = self.config.get("api_key", "")

        params = {
            "engine": "google",
            "q": "Apple Cider",
            "api_key": api_key
        }

        try:
            search = GoogleSearch(params)

            if search.get_response().status_code == 200:
                results = search.get_dict()
                organic_results = results["organic_results"]

                print(organic_results )

                tool_response = ToolResponse(data=organic_results )
                return tool_response
            else:
                print(f"Error: {search.get_response().status_code}")
                tool_response = ToolResponse(data={})
                return tool_response

        except requests.exceptions.RequestException as e:
            print(f"An error occurred: {e}")
            tool_response = ToolResponse({})
            return tool_response
