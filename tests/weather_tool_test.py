from vital_agent_resource_app.tools.tool_request import ToolRequest
from vital_agent_resource_app.tools.weather.weather_tool import WeatherTool


def main():
    print("Weather Tool Test")

    weather_tool = WeatherTool()

    data = {}

    tool_request = ToolRequest(data)

    tool_response = weather_tool.handle_tool_request(tool_request)


if __name__ == "__main__":
    main()
