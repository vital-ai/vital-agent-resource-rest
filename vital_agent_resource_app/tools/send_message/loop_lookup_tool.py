from vital_agent_resource_app.tools.abstract_tool import AbstractTool
from vital_agent_resource_app.tools.tool_request import ToolRequest
from vital_agent_resource_app.tools.tool_response import ToolResponse
from vital_agent_resource_app.tools.send_message.models import (
    LoopLookupSingleInput, LoopLookupBulkInput, LoopLookupStatusInput,
    LoopLookupSingleOutput, LoopLookupBulkOutput, LoopLookupStatusOutput,
    LoopLookupRequest, LoopLookupResult, LoopLookupError
)
from typing import List, Dict, Any, Union
import requests
import time
import logging

logger = logging.getLogger(__name__)


class LoopLookupTool(AbstractTool):
    """
    Loop Lookup Tool for checking iMessage reachability of phone numbers and emails.
    
    Supports:
    - Single contact lookup
    - Bulk contact lookup (up to 3000 contacts)
    - Status checking for submitted requests
    """

    def __init__(self, config: dict):
        super().__init__(config)
        self.api_key = config.get('api_key') if config else None
        self.base_url = "https://a.looplookup.com/api/v1"
        
        if not self.api_key:
            logger.warning("Loop Lookup API key not configured")

    def get_examples(self) -> List[Dict[str, Any]]:
        """Return list of example requests for Loop Lookup tool"""
        return [
            {
                "tool": "loop_lookup_tool",
                "tool_input": {
                    "contact": "+1 (323) 123-4567",
                    "region": "US",
                    "contact_details": True
                }
            },
            {
                "tool": "loop_lookup_tool",
                "tool_input": {
                    "contacts": ["+13231112233", "steve@mac.com", "1(787)111-22-33"],
                    "region": "US",
                    "contact_details": False
                }
            },
            {
                "tool": "loop_lookup_tool",
                "tool_input": {
                    "request_id": "2BC4FD6A-CE49-439F-81DF-E895C09CA49C"
                }
            }
        ]

    def handle_tool_request(self, tool_request: ToolRequest) -> ToolResponse:
        """Handle Loop Lookup tool requests"""
        start_time = time.time()
        
        if not self.api_key:
            return self._create_error_response("Loop Lookup API key not configured", start_time)
        
        try:
            validated_input = tool_request.tool_input
            
            # Determine request type based on input model
            if isinstance(validated_input, LoopLookupSingleInput):
                result = self._single_lookup(validated_input)
            elif isinstance(validated_input, LoopLookupBulkInput):
                result = self._bulk_lookup(validated_input)
            elif isinstance(validated_input, LoopLookupStatusInput):
                result = self._status_check(validated_input)
            else:
                return self._create_error_response("Invalid input type for Loop Lookup tool", start_time)
            
            return self._create_success_response(result, start_time)
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Loop Lookup API request error: {e}")
            return self._create_error_response(f"API request failed: {str(e)}", start_time)
        except Exception as e:
            logger.error(f"Loop Lookup tool error: {e}")
            return self._create_error_response(f"Tool error: {str(e)}", start_time)

    def _single_lookup(self, validated_input: LoopLookupSingleInput) -> dict:
        """Handle single contact lookup"""
        endpoint = "/lookup/"
        
        payload = {
            "contact": validated_input.contact
        }
        
        if validated_input.region:
            payload["region"] = validated_input.region
            
        if validated_input.contact_details:
            payload["contact_details"] = validated_input.contact_details
        
        logger.info(f"Performing single lookup for contact: {validated_input.contact}")
        
        response_data = self._make_api_request("POST", endpoint, payload)
        
        # Handle error response
        if not response_data.get("success", False):
            raise Exception(f"API Error {response_data.get('code', 'Unknown')}: {response_data.get('message', 'Unknown error')}")
        
        # Create request object
        request_obj = LoopLookupRequest(
            contact=response_data.get("contact", validated_input.contact),
            request_id=response_data.get("request_id", "")
        )
        
        # Create output
        output = LoopLookupSingleOutput(
            tool="loop_lookup_tool",
            success=True,
            request=request_obj
        )
        
        return output.dict()

    def _bulk_lookup(self, validated_input: LoopLookupBulkInput) -> dict:
        """Handle bulk contact lookup"""
        endpoint = "/lookup/"
        
        payload = {
            "contacts": validated_input.contacts
        }
        
        if validated_input.region:
            payload["region"] = validated_input.region
            
        if validated_input.contact_details:
            payload["contact_details"] = validated_input.contact_details
        
        logger.info(f"Performing bulk lookup for {len(validated_input.contacts)} contacts")
        
        response_data = self._make_api_request("POST", endpoint, payload)
        
        # Handle error response
        if not response_data.get("success", False):
            raise Exception(f"API Error {response_data.get('code', 'Unknown')}: {response_data.get('message', 'Unknown error')}")
        
        # Create request objects
        requests_list = []
        for request_data in response_data.get("requests", []):
            request_obj = LoopLookupRequest(
                contact=request_data.get("contact", ""),
                request_id=request_data.get("request_id", "")
            )
            requests_list.append(request_obj)
        
        # Create output
        output = LoopLookupBulkOutput(
            tool="loop_lookup_tool",
            success=True,
            requests=requests_list
        )
        
        return output.dict()

    def _status_check(self, validated_input: LoopLookupStatusInput) -> dict:
        """Handle status check for a request"""
        endpoint = f"/lookup/status/{validated_input.request_id}/"
        
        logger.info(f"Checking status for request ID: {validated_input.request_id}")
        
        response_data = self._make_api_request("GET", endpoint)
        
        # Create result object
        result_obj = LoopLookupResult(
            request_id=response_data.get("request_id", validated_input.request_id),
            status=response_data.get("status", "unknown"),
            contact=response_data.get("contact"),
            result_v1=response_data.get("result_v1")
        )
        
        # Create output
        output = LoopLookupStatusOutput(
            tool="loop_lookup_tool",
            result=result_obj
        )
        
        return output.dict()

    def _make_api_request(self, method: str, endpoint: str, data: dict = None) -> dict:
        """Make authenticated API request to Loop Lookup service"""
        url = f"{self.base_url}{endpoint}"
        
        headers = {
            "Authorization": self.api_key,
            "Content-Type": "application/json"
        }
        
        logger.debug(f"Making {method} request to {url}")
        
        try:
            if method.upper() == "GET":
                response = requests.get(url, headers=headers, timeout=30)
            elif method.upper() == "POST":
                response = requests.post(url, headers=headers, json=data, timeout=30)
            elif method.upper() == "DELETE":
                response = requests.delete(url, headers=headers, timeout=30)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
            
            logger.debug(f"Response status: {response.status_code}")
            
            # Handle HTTP errors
            if response.status_code == 400:
                error_data = response.json() if response.content else {}
                raise Exception(f"Bad Request: {error_data.get('message', 'Invalid request')}")
            elif response.status_code == 401:
                raise Exception("Unauthorized: Invalid API key")
            elif response.status_code == 402:
                raise Exception("Payment Required: No available requests/credits")
            elif response.status_code == 404:
                raise Exception("Not Found: Request ID not found")
            elif response.status_code == 500:
                raise Exception("Server Error: Loop Lookup service unavailable")
            elif response.status_code != 200:
                raise Exception(f"HTTP {response.status_code}: {response.text}")
            
            return response.json()
            
        except requests.exceptions.Timeout:
            raise Exception("Request timeout - Loop Lookup service did not respond in time")
        except requests.exceptions.ConnectionError:
            raise Exception("Connection error - Unable to reach Loop Lookup service")
        except requests.exceptions.RequestException as e:
            raise Exception(f"Request error: {str(e)}")
        except ValueError as e:
            if "JSON" in str(e):
                raise Exception("Invalid JSON response from Loop Lookup service")
            raise

    def _get_error_message(self, error_code: int) -> str:
        """Get human-readable error message for Loop Lookup error codes"""
        error_messages = {
            100: "Bad request",
            110: "Missing credentials in request",
            120: "One or more required parameters are missing",
            125: "Authorization key is invalid or does not exist",
            130: "Secret key is invalid or does not exist",
            150: "Missing recipient parameter in request",
            160: "Invalid recipient",
            170: "Invalid recipient email",
            180: "Invalid recipient phone number",
            190: "Phone number is not mobile",
            400: "No available requests/credits on your balance",
            500: "Your account is suspended",
            510: "Your account is blocked",
            530: "Your account is suspended due to debt"
        }
        
        return error_messages.get(error_code, f"Unknown error (code: {error_code})")

    def cancel_bulk_request(self, bulk_request_id: str) -> dict:
        """Cancel a bulk lookup request (utility method)"""
        endpoint = f"/bulk-lookup/delete/{bulk_request_id}/"
        
        logger.info(f"Canceling bulk request ID: {bulk_request_id}")
        
        try:
            response_data = self._make_api_request("DELETE", endpoint)
            return {
                "success": True,
                "message": f"Bulk request {bulk_request_id} canceled successfully",
                "data": response_data
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Failed to cancel bulk request: {str(e)}"
            }