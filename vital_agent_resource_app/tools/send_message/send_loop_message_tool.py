from vital_agent_resource_app.tools.abstract_tool import AbstractTool
from vital_agent_resource_app.tools.tool_request import ToolRequest
from vital_agent_resource_app.tools.tool_response import ToolResponse
from vital_agent_resource_app.tools.send_message.models import (
    LoopMessageSingleInput, LoopMessageGroupInput, LoopMessageAudioInput,
    LoopMessageReactionInput, LoopMessageStatusInput,
    LoopMessageSingleOutput, LoopMessageGroupOutput, LoopMessageStatusOutput,
    LoopMessageGroup, LoopMessageStatusResult, LoopMessageError
)
from typing import List, Dict, Any, Union
import requests
import time
import logging

logger = logging.getLogger(__name__)


class LoopMessageTool(AbstractTool):
    """
    Loop Message Tool for sending iMessages and SMS with support for:
    - Single messages with attachments and effects
    - Group messages to iMessage groups
    - Audio/voice messages
    - Tapback reactions
    - Message status checking
    """

    def __init__(self, config: dict):
        super().__init__(config)
        self.authorization_key = config.get('authorization_key') if config else None
        self.secret_key = config.get('secret_key') if config else None
        self.base_url = "https://server.loopmessage.com/api/v1"
        
        if not self.authorization_key or not self.secret_key:
            logger.warning("Loop Message API keys not configured")

    def get_examples(self) -> List[Dict[str, Any]]:
        """Return list of example requests for Loop Message tool"""
        return [
            {
                "tool": "loop_message_tool",
                "tool_input": {
                    "recipient": "+1 (323) 123-4567",
                    "text": "Hello from Loop Message!",
                    "sender_name": "MyApp",
                    "attachments": ["https://example.com/image.jpg"],
                    "effect": "balloons"
                }
            },
            {
                "tool": "loop_message_tool",
                "tool_input": {
                    "group": "2BC4FD6A-CE49-439F-81DF-E895C09CA49C",
                    "text": "Hello group!",
                    "sender_name": "MyApp"
                }
            },
            {
                "tool": "loop_message_tool",
                "tool_input": {
                    "recipient": "+1 (323) 123-4567",
                    "text": "Voice message",
                    "media_url": "https://example.com/audio.mp3",
                    "sender_name": "MyApp",
                    "audio_message": True
                }
            },
            {
                "tool": "loop_message_tool",
                "tool_input": {
                    "recipient": "+1 (323) 123-4567",
                    "text": "Reaction",
                    "message_id": "2BC4FD6A-CE49-439F-81DF-E895C09CA49C",
                    "sender_name": "MyApp",
                    "reaction": "love"
                }
            },
            {
                "tool": "loop_message_tool",
                "tool_input": {
                    "message_id": "2BC4FD6A-CE49-439F-81DF-E895C09CA49C"
                }
            }
        ]

    def handle_tool_request(self, tool_request: ToolRequest) -> ToolResponse:
        """Handle Loop Message tool requests"""
        start_time = time.time()
        
        if not self.authorization_key or not self.secret_key:
            return self._create_error_response("Loop Message API keys not configured", start_time)
        
        try:
            validated_input = tool_request.tool_input
            
            # Determine request type based on input model
            if isinstance(validated_input, LoopMessageSingleInput):
                result = self._send_single_message(validated_input)
            elif isinstance(validated_input, LoopMessageGroupInput):
                result = self._send_group_message(validated_input)
            elif isinstance(validated_input, LoopMessageAudioInput):
                result = self._send_audio_message(validated_input)
            elif isinstance(validated_input, LoopMessageReactionInput):
                result = self._send_reaction(validated_input)
            elif isinstance(validated_input, LoopMessageStatusInput):
                result = self._check_status(validated_input)
            else:
                return self._create_error_response("Invalid input type for Loop Message tool", start_time)
            
            return self._create_success_response(result, start_time)
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Loop Message API request error: {e}")
            return self._create_error_response(f"API request failed: {str(e)}", start_time)
        except Exception as e:
            logger.error(f"Loop Message tool error: {e}")
            return self._create_error_response(f"Tool error: {str(e)}", start_time)

    def _send_single_message(self, validated_input: LoopMessageSingleInput) -> dict:
        """Handle single message sending"""
        endpoint = "/message/send/"
        
        payload = {
            "recipient": validated_input.recipient,
            "text": validated_input.text,
            "sender_name": validated_input.sender_name
        }
        
        # Add optional parameters
        if validated_input.attachments:
            payload["attachments"] = validated_input.attachments
        if validated_input.timeout:
            payload["timeout"] = validated_input.timeout
        if validated_input.passthrough:
            payload["passthrough"] = validated_input.passthrough
        if validated_input.status_callback:
            payload["status_callback"] = validated_input.status_callback
        if validated_input.status_callback_header:
            payload["status_callback_header"] = validated_input.status_callback_header
        if validated_input.reply_to_id:
            payload["reply_to_id"] = validated_input.reply_to_id
        if validated_input.subject:
            payload["subject"] = validated_input.subject
        if validated_input.effect:
            payload["effect"] = validated_input.effect
        if validated_input.service and validated_input.service != "imessage":
            payload["service"] = validated_input.service
        
        logger.info(f"Sending single message to: {validated_input.recipient}")
        
        response_data = self._make_api_request("POST", endpoint, payload)
        
        # Handle error response
        if not response_data.get("success", False):
            raise Exception(f"API Error {response_data.get('code', 'Unknown')}: {response_data.get('message', 'Unknown error')}")
        
        # Create output
        output = LoopMessageSingleOutput(
            tool="loop_message_tool",
            success=True,
            message_id=response_data.get("message_id", ""),
            recipient=response_data.get("recipient", validated_input.recipient),
            text=response_data.get("text", validated_input.text)
        )
        
        return output.dict()

    def _send_group_message(self, validated_input: LoopMessageGroupInput) -> dict:
        """Handle group message sending"""
        endpoint = "/message/send/"
        
        payload = {
            "group": validated_input.group,
            "text": validated_input.text,
            "sender_name": validated_input.sender_name
        }
        
        # Add optional parameters
        if validated_input.attachments:
            payload["attachments"] = validated_input.attachments
        if validated_input.timeout:
            payload["timeout"] = validated_input.timeout
        if validated_input.passthrough:
            payload["passthrough"] = validated_input.passthrough
        if validated_input.status_callback:
            payload["status_callback"] = validated_input.status_callback
        if validated_input.status_callback_header:
            payload["status_callback_header"] = validated_input.status_callback_header
        
        logger.info(f"Sending group message to group: {validated_input.group}")
        
        response_data = self._make_api_request("POST", endpoint, payload)
        
        # Handle error response
        if not response_data.get("success", False):
            raise Exception(f"API Error {response_data.get('code', 'Unknown')}: {response_data.get('message', 'Unknown error')}")
        
        # Create group object from response
        group_data = response_data.get("group", {})
        group_obj = LoopMessageGroup(
            group_id=group_data.get("group_id", validated_input.group),
            name=group_data.get("name"),
            participants=group_data.get("participants", [])
        )
        
        # Create output
        output = LoopMessageGroupOutput(
            tool="loop_message_tool",
            success=True,
            message_id=response_data.get("message_id", ""),
            group=group_obj,
            text=response_data.get("text", validated_input.text)
        )
        
        return output.dict()

    def _send_audio_message(self, validated_input: LoopMessageAudioInput) -> dict:
        """Handle audio message sending"""
        endpoint = "/message/send/"
        
        payload = {
            "recipient": validated_input.recipient,
            "text": validated_input.text,
            "media_url": validated_input.media_url,
            "sender_name": validated_input.sender_name,
            "audio_message": validated_input.audio_message
        }
        
        # Add optional parameters
        if validated_input.status_callback:
            payload["status_callback"] = validated_input.status_callback
        if validated_input.status_callback_header:
            payload["status_callback_header"] = validated_input.status_callback_header
        if validated_input.passthrough:
            payload["passthrough"] = validated_input.passthrough
        
        logger.info(f"Sending audio message to: {validated_input.recipient}")
        
        response_data = self._make_api_request("POST", endpoint, payload)
        
        # Handle error response
        if not response_data.get("success", False):
            raise Exception(f"API Error {response_data.get('code', 'Unknown')}: {response_data.get('message', 'Unknown error')}")
        
        # Create output (using single message output for audio messages)
        output = LoopMessageSingleOutput(
            tool="loop_message_tool",
            success=True,
            message_id=response_data.get("message_id", ""),
            recipient=response_data.get("recipient", validated_input.recipient),
            text=response_data.get("text", validated_input.text)
        )
        
        return output.dict()

    def _send_reaction(self, validated_input: LoopMessageReactionInput) -> dict:
        """Handle reaction sending"""
        endpoint = "/message/send/"
        
        payload = {
            "recipient": validated_input.recipient,
            "text": validated_input.text,
            "message_id": validated_input.message_id,
            "sender_name": validated_input.sender_name,
            "reaction": validated_input.reaction
        }
        
        # Add optional parameters
        if validated_input.status_callback:
            payload["status_callback"] = validated_input.status_callback
        if validated_input.status_callback_header:
            payload["status_callback_header"] = validated_input.status_callback_header
        if validated_input.passthrough:
            payload["passthrough"] = validated_input.passthrough
        
        logger.info(f"Sending reaction '{validated_input.reaction}' to message {validated_input.message_id}")
        
        response_data = self._make_api_request("POST", endpoint, payload)
        
        # Handle error response
        if not response_data.get("success", False):
            raise Exception(f"API Error {response_data.get('code', 'Unknown')}: {response_data.get('message', 'Unknown error')}")
        
        # Create output (using single message output for reactions)
        output = LoopMessageSingleOutput(
            tool="loop_message_tool",
            success=True,
            message_id=response_data.get("message_id", ""),
            recipient=response_data.get("recipient", validated_input.recipient),
            text=response_data.get("text", validated_input.text)
        )
        
        return output.dict()

    def _check_status(self, validated_input: LoopMessageStatusInput) -> dict:
        """Handle status check for a message"""
        endpoint = f"/message/status/{validated_input.message_id}/"
        
        logger.info(f"Checking status for message ID: {validated_input.message_id}")
        
        response_data = self._make_api_request("GET", endpoint)
        
        # Create result object
        result_obj = LoopMessageStatusResult(
            message_id=response_data.get("message_id", validated_input.message_id),
            status=response_data.get("status", "unknown"),
            recipient=response_data.get("recipient"),
            text=response_data.get("text"),
            sandbox=response_data.get("sandbox"),
            error_code=response_data.get("error_code"),
            sender_name=response_data.get("sender_name"),
            passthrough=response_data.get("passthrough"),
            last_update=response_data.get("last_update")
        )
        
        # Create output
        output = LoopMessageStatusOutput(
            tool="loop_message_tool",
            result=result_obj
        )
        
        return output.dict()

    def _make_api_request(self, method: str, endpoint: str, data: dict = None) -> dict:
        """Make authenticated API request to Loop Message service"""
        url = f"{self.base_url}{endpoint}"
        
        headers = {
            "Authorization": self.authorization_key,
            "Loop-Secret-Key": self.secret_key,
            "Content-Type": "application/json"
        }
        
        logger.debug(f"Making {method} request to {url}")
        
        try:
            if method.upper() == "GET":
                response = requests.get(url, headers=headers, timeout=30)
            elif method.upper() == "POST":
                response = requests.post(url, headers=headers, json=data, timeout=30)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
            
            logger.debug(f"Response status: {response.status_code}")
            
            # Handle HTTP errors
            if response.status_code == 400:
                error_data = response.json() if response.content else {}
                raise Exception(f"Bad Request: {error_data.get('message', 'Invalid request')}")
            elif response.status_code == 401:
                raise Exception("Unauthorized: Invalid authorization key")
            elif response.status_code == 402:
                raise Exception("Payment Required: No available requests/credits")
            elif response.status_code == 404:
                raise Exception("Not Found: Message ID not found")
            elif response.status_code == 500:
                raise Exception("Server Error: Loop Message service unavailable")
            elif response.status_code != 200:
                raise Exception(f"HTTP {response.status_code}: {response.text}")
            
            return response.json()
            
        except requests.exceptions.Timeout:
            raise Exception("Request timeout - Loop Message service did not respond in time")
        except requests.exceptions.ConnectionError:
            raise Exception("Connection error - Unable to reach Loop Message service")
        except requests.exceptions.RequestException as e:
            raise Exception(f"Request error: {str(e)}")
        except ValueError as e:
            if "JSON" in str(e):
                raise Exception("Invalid JSON response from Loop Message service")
            raise

    def _get_error_message(self, error_code: int) -> str:
        """Get human-readable error message for Loop Message error codes"""
        error_messages = {
            100: "Bad request",
            110: "Missing credentials in request",
            120: "One or more required parameters are missing",
            125: "Authorization key is invalid or does not exist",
            130: "Secret key is invalid or does not exist",
            140: "No text parameter in request",
            150: "No recipient parameter in request",
            160: "Invalid recipient",
            170: "Invalid recipient email",
            180: "Invalid recipient phone number",
            190: "Phone number is not mobile",
            210: "Sender name not specified in request parameters",
            220: "Invalid sender name",
            230: "Internal error occurred while trying to use the specified sender name",
            240: "Sender name is not activated or unpaid",
            270: "This recipient blocked any type of messages",
            300: "Unable to send this type of message without dedicated sender name",
            330: "You send messages too frequently to recipients you haven't contacted for a long time",
            400: "No available requests/credits on your balance",
            500: "Your account is suspended",
            510: "Your account is blocked",
            530: "Your account is suspended due to debt",
            540: "No active purchased sender name to send message",
            545: "Your sender name has been suspended by Apple",
            550: "Requires a dedicated sender name or need to add this recipient as sandbox contact",
            560: "Unable to send outbound messages until this recipient initiates a conversation with your sender",
            570: "This API request is deprecated and not supported",
            580: "Invalid effect parameter",
            590: "Invalid message_id for reply",
            595: "Invalid or non-existent message_id",
            600: "Invalid reaction parameter",
            610: "Reaction or message_id is invalid or does not exist",
            620: "Unable to use effect and reaction parameters in the same request",
            630: "Need to set up a vCard file for this sender name in the dashboard",
            640: "No media file URL - media_url",
            1110: "Unable to send SMS if the recipient is an email address",
            1120: "Unable to send SMS if the recipient is group",
            1130: "Unable to send SMS with marketing content",
            1140: "Unable to send audio messages through SMS"
        }
        
        return error_messages.get(error_code, f"Unknown error (code: {error_code})")