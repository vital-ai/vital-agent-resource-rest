import json
from vital_agent_resource_app.tools.abstract_tool import AbstractTool
from vital_agent_resource_app.tools.tool_request import ToolRequest
from vital_agent_resource_app.tools.tool_response import ToolResponse
import requests

class AmazonProductSearchTool(AbstractTool):

    def handle_tool_request(self, tool_request: ToolRequest) -> ToolResponse:

        request_data = tool_request.request_data

        tool_response = self.amazon_product_search()

        return tool_response

    def amazon_product_search(self):

        api_key = self.config.get("api_key", "")

        params = {
            'api_key': api_key,
            'type': 'search',
            'amazon_domain': 'amazon.com',
            'search_term': 'red dress'
        }

        try:

            response = requests.get('https://api.rainforestapi.com/request', params)

            print(f"GET: {response.url}")
            print(f"Response: {response.status_code}")

            if response.status_code == 200:
                response_content = response.json()
                print(response_content)
                tool_response = ToolResponse(data=response_content)
                return tool_response
            else:
                print(f"Error: {response.status_code}")
                tool_response = ToolResponse(data={})
                return tool_response

        except requests.exceptions.RequestException as e:
            print(f"An error occurred: {e}")
            tool_response = ToolResponse({})
            return tool_response
