from vital_agent_resource_app.tools.abstract_tool import AbstractTool
from vital_agent_resource_app.tools.tool_request import ToolRequest
from vital_agent_resource_app.tools.tool_response import ToolResponse
import requests


class WeatherTool(AbstractTool):

    def __init__(self):
        pass

    def handle_tool_request(self, tool_request: ToolRequest) -> ToolResponse:

        tool_request = {
            "location": "Your Location",
            "latitude": 40.7128,
            "longitude": -74.0060
        }

        latitude = tool_request["latitude"]
        longitude = tool_request["longitude"]

        weather_url = "https://api.open-meteo.com/v1/forecast"

        current_param_list = [
            "weather_code",
            "temperature_2m",
            "relative_humidity_2m",
            "apparent_temperature",
            "is_day",
            "precipitation",
            "cloud_cover",
            "wind_speed_10m",
            "wind_direction_10m",
            "wind_gusts_10m"
        ]

        daily_param_list = [
            "weather_code",
            "temperature_2m_max",
            "temperature_2m_min",
            "apparent_temperature_max",
            "apparent_temperature_min",
            "sunrise",
            "sunset"
        ]

        params = {
            "latitude": str(latitude),
            "longitude": str(longitude),
            "timezone": "America/New_York",
            "temperature_unit": "fahrenheit",
            "wind_speed_unit": "mph",
            "precipitation_unit": "inch",
            "daily": ",".join(daily_param_list),
            "current": ",".join(current_param_list)
        }

        try:
            response = requests.get(weather_url, params=params)
            print(f"GET: {response.url}")
            print(f"Response: {response.status_code}")

            if response.status_code == 200:
                response_content = response.json()
                print(response_content)
                tool_response = ToolResponse(data=response_content)
                return tool_response
            else:
                print(f"Error: {response.status_code}")
                tool_response = ToolResponse()
                return tool_response
        except requests.exceptions.RequestException as e:
            print(f"An error occurred: {e}")
            tool_response = ToolResponse()
            return tool_response




