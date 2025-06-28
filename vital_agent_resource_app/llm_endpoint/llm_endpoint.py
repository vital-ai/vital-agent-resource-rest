import asyncio
import logging
from typing import Union, AsyncGenerator
import httpx
from fastapi import Request
from vital_llm_cluster_mgr.vital_llm_cluster_mgr import VitalLLMClusterMgr
from vital_llm_cluster_mgr.vllm_interface import CompletionResponse, ErrorResponse

class LLMEndpoint:

    @classmethod
    async def handle_llm_request(
            cls, cluster_mgr: VitalLLMClusterMgr, raw_request: Request
    ) -> Union[AsyncGenerator[str, None], CompletionResponse, ErrorResponse]:
        try:
            json_body = await raw_request.json()
        except Exception as e:
            return ErrorResponse(
                message=f"Invalid JSON: {str(e)}",
                type="invalid_request",
                code=400,
            )

        uvicorn_logger = logging.getLogger("uvicorn.error")

        stream_flag = json_body.get("stream", False)

        # get this from cluster mgr
        # if no servers deployed, return an error

        running_pods = cluster_mgr.get_running_pods()

        if running_pods is None or len(running_pods) == 0:
            return ErrorResponse(
                message="No servers available",
                type="no_servers",
                code=404,
            )

        # get one, this should be randomized, and pick one with the right model
        running_pod = running_pods[0]

        pod_id = running_pod.get("id")

        uvicorn_logger.info(f"using pod_id: {pod_id}")

        if not pod_id:
            return ErrorResponse(
                message="No servers available",
                type="no_servers",
                code=404,
            )

        endpoint_url = f"https://{pod_id}-8000.proxy.runpod.net/v1/completions"

        authorization = raw_request.headers.get("authorization")
        content_type = raw_request.headers.get("content-type", "application/json")
        organization = raw_request.headers.get("openai-organization")

        headers = {
            "Authorization": authorization,
            "Content-Type": content_type,
        }
        if organization:
            headers["OpenAI-Organization"] = organization

        if stream_flag:
            async def stream_generator() -> AsyncGenerator[str, None]:
                # The client and streaming response remain open for the lifetime of the generator.
                async with httpx.AsyncClient(timeout=None) as client:
                    async with client.stream("POST", endpoint_url, json=json_body, headers=headers) as resp:
                        if resp.status_code != 200:
                            error_text = (await resp.aread()).decode("utf-8", errors="replace")
                            # Optionally, yield an error message or simply break.
                            yield f"Error from endpoint: {error_text}"
                            return
                        try:
                            async for chunk in resp.aiter_text():
                                yield chunk
                        except (httpx.StreamClosed, asyncio.CancelledError) as exc:
                            # Log the exception if needed and exit gracefully.
                            # For example: logging.warning("Streaming aborted: %s", exc)
                            return

            return stream_generator()

        else:
            async with httpx.AsyncClient(timeout=None) as client:
                response = await client.post(endpoint_url, json=json_body, headers=headers)
            if response.status_code != 200:
                return ErrorResponse(
                    message=f"Error from endpoint: {response.text}",
                    type="endpoint_error",
                    code=response.status_code,
                )
            response_json = response.json()
            return CompletionResponse.parse_obj(response_json)