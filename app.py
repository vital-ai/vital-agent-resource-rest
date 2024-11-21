import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from vital_agent_resource_app.tools.amazon_shopping.amazon_product_search_tool import AmazonProductSearchTool
from vital_agent_resource_app.tools.place_search.place_search_tool import PlaceSearchTool
from vital_agent_resource_app.tools.tool_request import ToolRequest
from vital_agent_resource_app.tools.weather.weather_tool import WeatherTool
from vital_agent_resource_app.tools.web_search.google_web_search_tool import GoogleWebSearchTool
from vital_agent_resource_app.utils.config_utils import ConfigUtils

app = FastAPI()


def get_tool_by_id(config_dict, tool_id):
    tools = config_dict.get('vital_agent_resource_app', {}).get('tools', [])
    for tool in tools:
        if tool.get('tool_id') == tool_id:
            return tool
    return None


config = ConfigUtils.load_config()

weather_config = get_tool_by_id(config, 'weather_tool')

place_search_config = get_tool_by_id(config, 'place_search_tool')

amazon_product_search_config = get_tool_by_id(config, 'amazon_product_search_tool')

google_web_search_config = get_tool_by_id(config, 'google_web_search_tool')

tools_map = {
    "weather_tool": WeatherTool(weather_config),
    "place_search_tool": PlaceSearchTool(place_search_config),
    "amazon_product_search_tool": AmazonProductSearchTool(amazon_product_search_config),
    "google_web_search_tool": GoogleWebSearchTool(google_web_search_config)
}


@app.get("/health")
async def health_check():
    return {"status": "ok"}


@app.post("/tool")
async def handle_tool_request(request: Request):

    request_data = await request.json()

    tool_name = request_data.get("tool")

    if not tool_name:
        raise HTTPException(status_code=400, detail="Missing 'tool' key in request data")

    tool_instance = tools_map.get(tool_name)

    if not tool_instance:
        raise HTTPException(status_code=404, detail=f"Tool '{tool_name}' not found")

    tool_parameters = request_data.get("tool_parameters")

    tool_request = ToolRequest(data=tool_parameters)

    response = tool_instance.handle_tool_request(tool_request)

    return JSONResponse(content=response.to_dict())


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8008)

