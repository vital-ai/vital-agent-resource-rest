from vital_agent_resource_app.tools.abstract_tool import AbstractTool
from vital_agent_resource_app.tools.tool_request import ToolRequest
from vital_agent_resource_app.tools.tool_response import ToolResponse
import requests


class WeatherTool(AbstractTool):

    def handle_tool_request(self, tool_request: ToolRequest) -> ToolResponse:

        request_data = tool_request.request_data

        latitude = request_data["latitude"]
        longitude = request_data["longitude"]
        include_previous = request_data.get("include_previous", False)
        use_archive = request_data.get("use_archive", False)
        archive_date = request_data.get("archive_date", "")

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




