from vital_agent_resource_app.tools.abstract_tool import AbstractTool
from vital_agent_resource_app.tools.tool_request import ToolRequest
from vital_agent_resource_app.tools.tool_response import ToolResponse
from typing import List, Dict, Any
import requests


class WeatherTool(AbstractTool):

    def get_examples(self) -> List[Dict[str, Any]]:
        """Return list of example requests for Weather tool"""
        return [
            {
                "tool": "weather_tool",
                "tool_input": {
                    "latitude": 40.7128,
                    "longitude": -74.0060
                }
            },
            {
                "tool": "weather_tool",
                "tool_input": {
                    "latitude": 37.7749,
                    "longitude": -122.4194,
                    "include_previous": True
                }
            }
        ]

    def handle_tool_request(self, tool_request: ToolRequest) -> ToolResponse:
        import time
        start_time = time.time()
        
        # Extract parameters from validated tool input
        validated_input = tool_request.tool_input
        latitude = validated_input.latitude
        longitude = validated_input.longitude
        include_previous = validated_input.include_previous or False
        use_archive = validated_input.use_archive or False
        archive_date = validated_input.archive_date or ""

        # include_previous
        # past_days=10

        # or archive endpoint
        # $ curl "https://archive-api.open-meteo.com/v1/era5?latitude=52.52&longitude=13.41&start_date=2021-01-01&end_date=2021-12-31

        # archive case
        if use_archive and archive_date:

            weather_url = f"https://archive-api.open-meteo.com/v1/era5"

            daily_param_list = [
                "weather_code",
                "temperature_2m_max",
                "temperature_2m_min",
                "apparent_temperature_max",
                "apparent_temperature_min",
                "sunrise",
                "sunset",
                "precipitation_sum",
                "precipitation_hours",
                "precipitation_probability_max",
                "precipitation_probability_min",
                "precipitation_probability_mean",
                "daylight_duration",
                "uv_index_max",
                "wind_gusts_10m_max",
            ]

            params = {
                "start_date": str(archive_date),
                "end_date": str(archive_date),
                "latitude": str(latitude),
                "longitude": str(longitude),
                "timezone": "America/New_York",
                "temperature_unit": "fahrenheit",
                "wind_speed_unit": "mph",
                "precipitation_unit": "inch",
                "daily": ",".join(daily_param_list),
            }

            try:
                response = requests.get(weather_url, params=params)
                print(f"GET: {response.url}")
                print(f"Response: {response.status_code}")

                if response.status_code == 200:
                    response_content = response.json()
                    print(response_content)
                    
                    # Create structured output using the registered model
                    from vital_agent_resource_app.tools.weather.models import WeatherOutput, WeatherData
                    weather_data = WeatherData(**response_content)
                    tool_output = WeatherOutput(
                        tool="weather_tool",
                        weather_data=weather_data
                    )
                    
                    return self._create_success_response(tool_output.dict(), start_time)
                else:
                    print(f"Error: {response.status_code}")
                    return self._create_error_response(f"Weather API error: {response.status_code}", start_time)
            except requests.exceptions.RequestException as e:
                print(f"An error occurred: {e}")
                return self._create_error_response(f"Request error: {str(e)}", start_time)

        # normal case
        weather_url = "https://api.open-meteo.com/v1/forecast"

        current_param_list = [
            "weather_code",
            "temperature_2m",
            "relative_humidity_2m",
            "apparent_temperature",
            "is_day",
            "precipitation",
            "precipitation_probability",
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
            "sunset",
            "precipitation_sum",
            "precipitation_hours",
            "precipitation_probability_max",
            "precipitation_probability_min",
            "precipitation_probability_mean",
            "daylight_duration",
            "uv_index_max",
            "wind_gusts_10m_max",
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

        if include_previous:
            params["past_days"] = 10

        try:
            # print(params)
            response = requests.get(weather_url, params=params)
            print(f"GET: {response.url}")
            print(f"Response: {response.status_code}")

            if response.status_code == 200:
                response_content = response.json()
                print(response_content)
                
                # Create structured output using the registered model
                from vital_agent_resource_app.tools.weather.models import WeatherOutput, WeatherData
                weather_data = WeatherData(**response_content)
                tool_output = WeatherOutput(
                    tool="weather_tool",
                    weather_data=weather_data
                )
                
                return self._create_success_response(tool_output.dict(), start_time)
            else:
                print(f"Error: {response.status_code}")
                return self._create_error_response(f"Weather API error: {response.status_code}", start_time)
        except requests.exceptions.RequestException as e:
            print(f"An error occurred: {e}")
            return self._create_error_response(f"Request error: {str(e)}", start_time)




