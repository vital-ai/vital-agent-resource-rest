import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from vital_agent_resource_app.tools.tool_request import ToolRequest
from vital_agent_resource_app.tools.weather.weather_tool import WeatherTool

app = FastAPI()


tools_map = {
    "weather_tool": WeatherTool()
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

    tool_request = ToolRequest(data=request_data)

    response = tool_instance.handle_tool_request(tool_request)

    return JSONResponse(content=response.to_dict())


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8008)

