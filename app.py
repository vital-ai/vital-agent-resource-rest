import asyncio
import logging
import uuid
from typing import Optional, List, Union, Dict
import time
from dataclasses import dataclass, field
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from vital_llm_cluster_mgr.vital_llm_cluster_mgr import VitalLLMClusterMgr
from vital_llm_cluster_mgr.vllm_interface import with_cancellation, ErrorResponse, CompletionResponse

from vital_agent_resource_app.llm_endpoint.llm_endpoint import LLMEndpoint
from vital_agent_resource_app.tools.amazon_shopping.amazon_product_search_tool import AmazonProductSearchTool
from vital_agent_resource_app.tools.place_search.place_search_tool import PlaceSearchTool
from vital_agent_resource_app.tools.tool_request import ToolRequest
from vital_agent_resource_app.tools.weather.weather_tool import WeatherTool
from vital_agent_resource_app.tools.web_search.google_web_search_tool import GoogleWebSearchTool
from vital_agent_resource_app.utils.config_utils import ConfigUtils
import functools
from pydantic import BaseModel, ConfigDict, Field, model_validator
from fastapi.responses import JSONResponse, Response, StreamingResponse


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

app_config = config.get('vital_agent_resource_app', {})

runpod_config = app_config.get('runpod', {})

runpod_api_key = runpod_config.get('runpod_api_key', "")

logging.info("starting cluster manager.")

cluster_mgr = VitalLLMClusterMgr(runpod_api_key=runpod_api_key)

# for direct use of the LLMs via the public api
# the path should be:
# public API (ALB) -->
# gateway (ECS/kong) -->
# agent-rest-resource (ALB) -->
# agent-rest-resource (ECS + cluster-mgr) -->
# vital-llm-reasoner-server (runpod)

# the agent-rest-resource (ALB) could
# potentially be replaced with AWS ECS Service Discovery (Cloud Map)
# since that is meant to be a simple round-robin lookup
# or lua could look up the IP addresses of the tasks on the cluster
# but that may not be simple
# need to check how much the service discovery stays current upon changes
# as the ALB can be self-corrective on failures, so that might be more stable anyway

# dns method doesn't seem to work as it doesn't do round-robin due to caching
# not sure how lua can access the ecs info via epi

# cluster manager moved into tool service which has an ALB, so using that for now

# define endpoint-test.apivitalai.com to use for testing

# an agent calling tools would call the same, but originating
# from the container associated with the agent and
# the JWT would be used for authorization

# an agent calling the LLMs would call the same path also
# however the endpoint would be slightly different so that the JWT
# can be used for authorization instead of the API Key

# the gateway sends usage data for logging, analysis, and billing
# so everything is routed through it

# activity occurring within the vLLM that should be captured for usage
# should send rest request via the same path to the "usage" tool
# enabling the gateway to capture it, with the usage tool just logging
# this accounts for python code execution within the vLLM having
# a usage call to capture that activity

# previously the plan was for the gateway to directly communicate with the vLLM servers
# but it may be easier to embed the cluster manager here and use this as the proxy
# rather than try to have the gateway lua plugin make that decision.



@app.get("/health")
async def health_check():
    return {"status": "ok"}


# this acts as a proxy, and re-uses the headers on the request
@app.post("/v1/completions")
@with_cancellation
async def handle_completions_request(raw_request: Request):

    global cluster_mgr

    generator = await LLMEndpoint.handle_llm_request(cluster_mgr, raw_request)

    if isinstance(generator, ErrorResponse):
        return JSONResponse(content=generator.model_dump(),
                            status_code=generator.code)
    elif isinstance(generator, CompletionResponse):
        return JSONResponse(content=generator.model_dump())

    return StreamingResponse(content=generator, media_type="text/event-stream")


# enforce access via JWT
# TODO endpoint for warming up an instance of particular type/model/size/gpu type
# such as A100 for the R1-Qwen Model with 48GB


# enforce access via JWT
# TODO add endpoint for shutting down instance(s) that aren't needed

# enforce with JWT
# get list of current instances running


# enforce with JWT
# admin calls to get list of tools


# this should enforce access by checking the JWT
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

    logging.basicConfig(level=logging.INFO)

    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    uvicorn.run(app, host="0.0.0.0", port=8008)

