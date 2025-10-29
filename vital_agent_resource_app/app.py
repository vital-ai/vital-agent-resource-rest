import asyncio
import logging
import uuid
from typing import Optional, List, Union, Dict
import time
from dataclasses import dataclass, field
import uvicorn
from fastapi import FastAPI, HTTPException, Request, Depends, status
from fastapi.responses import JSONResponse, Response, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import asyncio
import signal
import sys
import os

logger = logging.getLogger("VitalAgentContainerLogger")

from vital_llm_cluster_mgr.vital_llm_cluster_mgr import VitalLLMClusterMgr
from vital_llm_cluster_mgr.vllm_interface import with_cancellation, ErrorResponse, CompletionResponse

from vital_agent_resource_app.llm_endpoint.llm_endpoint import LLMEndpoint
from vital_agent_resource_app.tools.amazon_shopping.amazon_product_search_tool import AmazonProductSearchTool
from vital_agent_resource_app.tools.google_address_validation.google_address_validation_tool import GoogleAddressValidationTool
from vital_agent_resource_app.tools.place_search.place_search_tool import PlaceSearchTool
from vital_agent_resource_app.tools.tool_request import ToolRequest
from vital_agent_resource_app.tools.tool_response import ToolResponse
from vital_agent_resource_app.tools.tool_name_enum import ToolName

# Import all tool models to ensure they appear in FastAPI docs
from vital_agent_resource_app.tools.google_address_validation.models import (
    AddressValidationInput, AddressValidationOutput, AddressValidationResult, AddressComponent
)
from vital_agent_resource_app.tools.place_search.models import (
    PlaceSearchInput, PlaceSearchOutput, PlaceDetails
)
from vital_agent_resource_app.tools.weather.models import (
    WeatherInput, WeatherOutput, WeatherData
)
from vital_agent_resource_app.tools.web_search.models import (
    WebSearchInput, WebSearchOutput, WebSearchResult
)
from vital_agent_resource_app.tools.send_message.models import (
    LoopLookupSingleInput, LoopLookupBulkInput, LoopLookupStatusInput,
    LoopLookupSingleOutput, LoopLookupBulkOutput, LoopLookupStatusOutput,
    LoopLookupInput, LoopLookupOutput,
    LoopMessageSingleInput, LoopMessageGroupInput, LoopMessageAudioInput,
    LoopMessageReactionInput, LoopMessageStatusInput,
    LoopMessageSingleOutput, LoopMessageGroupOutput, LoopMessageStatusOutput,
    LoopMessageInput, LoopMessageOutput
)
from vital_agent_resource_app.tools.send_email.models import (
    EmailInput, EmailOutput
)
from vital_agent_resource_app.tools.weather.weather_tool import WeatherTool
from vital_agent_resource_app.tools.web_search.google_web_search_tool import GoogleWebSearchTool
from vital_agent_resource_app.tools.send_message.loop_lookup_tool import LoopLookupTool
from vital_agent_resource_app.tools.send_message.send_loop_message_tool import LoopMessageTool
from vital_agent_resource_app.tools.send_email.send_email_tool import SendEmailTool

# Import model modules to register tools
from vital_agent_resource_app.tools.google_address_validation import models as address_models
from vital_agent_resource_app.tools.place_search import models as place_models
from vital_agent_resource_app.tools.weather import models as weather_models
from vital_agent_resource_app.tools.web_search import models as web_search_models
from vital_agent_resource_app.tools.send_message import models as loop_lookup_models
from vital_agent_resource_app.utils.config_utils import ConfigUtils
import functools
from pydantic import BaseModel, ConfigDict, Field, model_validator
from fastapi.responses import JSONResponse, Response, StreamingResponse
# Create and populate tool registry
from vital_agent_resource_app.tools.tool_registry import ToolRegistry

# Import authentication components
from vital_agent_resource_app.auth.dependencies import get_current_user_dependency
from vital_agent_resource_app.data_models.auth_models import AuthenticatedUser
from vital_agent_resource_app.auth.middleware import JWTAuthenticationMiddleware



def get_tool_by_id(config_dict, tool_id):
    tools = config_dict.get('vital_agent_resource_app', {}).get('tools', [])
    for tool in tools:
        if tool.get('tool_id') == tool_id:
            return tool
    return None


config = ConfigUtils.load_config()

weather_config = get_tool_by_id(config, 'weather_tool')

place_search_config = get_tool_by_id(config, 'place_search_tool')

# amazon_product_search_config = get_tool_by_id(config, 'amazon_product_search_tool')

google_web_search_config = get_tool_by_id(config, 'google_web_search_tool')

google_address_validation_config = get_tool_by_id(config, 'google_address_validation_tool')

loop_lookup_config = get_tool_by_id(config, 'loop_lookup_tool')

loop_message_config = get_tool_by_id(config, 'loop_message_tool')

send_email_config = get_tool_by_id(config, 'send_email_tool')


# Instantiate tool registry
tool_registry = ToolRegistry()

# Add tools to registry with their models and instances
tool_registry.add_tool(
    tool_name=ToolName.weather_tool.value,
    input_model=WeatherInput,
    output_model=WeatherOutput,
    tool_instance=WeatherTool(weather_config)
)

tool_registry.add_tool(
    tool_name=ToolName.place_search_tool.value, 
    input_model=PlaceSearchInput,
    output_model=PlaceSearchOutput,
    tool_instance=PlaceSearchTool(place_search_config)
)

tool_registry.add_tool(
    tool_name=ToolName.google_address_validation_tool.value,
    input_model=AddressValidationInput,
    output_model=AddressValidationOutput,
    tool_instance=GoogleAddressValidationTool(google_address_validation_config)
)

tool_registry.add_tool(
    tool_name=ToolName.google_web_search_tool.value,
    input_model=WebSearchInput,
    output_model=WebSearchOutput,
    tool_instance=GoogleWebSearchTool(google_web_search_config)
)

tool_registry.add_tool(
    tool_name=ToolName.loop_lookup_tool.value,
    input_model=LoopLookupInput,
    output_model=LoopLookupOutput,
    tool_instance=LoopLookupTool(loop_lookup_config)
)

tool_registry.add_tool(
    tool_name=ToolName.loop_message_tool.value,
    input_model=LoopMessageInput,
    output_model=LoopMessageOutput,
    tool_instance=LoopMessageTool(loop_message_config)
)

tool_registry.add_tool(
    tool_name=ToolName.send_email_tool.value,
    input_model=EmailInput,
    output_model=EmailOutput,
    tool_instance=SendEmailTool(send_email_config)
)

app = FastAPI()

# Add JWT authentication middleware
app.add_middleware(JWTAuthenticationMiddleware)


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
async def handle_completions_request(
    raw_request: Request,
    current_user: AuthenticatedUser = Depends(get_current_user_dependency)
):
    """LLM completions endpoint with JWT authentication"""
    global cluster_mgr

    # Log the authenticated request
    logger.info(f"LLM completion request from user: {current_user.user_id}")

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
@app.post("/tool", response_model=ToolResponse, tags=["Tools"])
async def handle_tool_request(
    request: ToolRequest,
    current_user: AuthenticatedUser = Depends(get_current_user_dependency)
):
    import time
    start_time = time.time()
    
    try:
        # Log the authenticated tool request
        logger.info(f"Tool request from user: {current_user.user_id}, tool: {request.tool}")
        
        # Extract tool name and tool_input from request
        tool_name = request.tool
        validated_input = request.tool_input  # Already validated by Pydantic
        
        tool_instance = tool_registry.get_tool_instance(tool_name)
        if not tool_instance:
            raise HTTPException(status_code=404, detail=f"Tool '{tool_name}' not found")
        
        # Create ToolRequest with validated input
        tool_request = ToolRequest(
            tool=tool_name,
            request_id=request.request_id,
            timeout=request.timeout,
            tool_input=validated_input
        )
        
        # Execute tool
        response = tool_instance.handle_tool_request(tool_request)
        
        # Calculate duration
        duration_ms = int((time.time() - start_time) * 1000)
        
        # Update response with duration if not already set
        if hasattr(response, 'duration_ms') and response.duration_ms == 0:
            response.duration_ms = duration_ms
        
        return JSONResponse(content=response.to_dict())
        
    except HTTPException:
        raise
    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        error_response = ToolResponse.create_error(str(e), duration_ms)
        return JSONResponse(content=error_response.to_dict(), status_code=500)


if __name__ == "__main__":

    logging.basicConfig(level=logging.INFO)

    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    uvicorn.run(app, host="0.0.0.0", port=8008)

