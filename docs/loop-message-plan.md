# Loop Message Tool Implementation Plan

## Overview
Implementation plan for integrating the Loop Message API into the Vital Agent Resource REST system. The Loop Message API provides iMessage and SMS sending capabilities with support for text messages, attachments, audio messages, reactions, and group messaging.

## API Analysis

### Base URL
- Production: `https://server.loopmessage.com/api/v1/`

### Authentication
- **Headers**: 
  - `Authorization: {AUTHORIZATION_KEY}` (no Bearer prefix required)
  - `Loop-Secret-Key: {API_SECRET_KEY}`
- **Content-Type**: `application/json`
- **Protocol**: HTTPS only (minimum TLS v1.2)
- **Supported Ports**: 443, 2053, 2083, 2087, 2096, 8443

### Endpoints

#### 1. Send Single Message
- **Method**: `POST /message/send/`
- **Purpose**: Send text message with optional attachments to individual recipient
- **Parameters**:
  - `recipient` (required): Phone number or email
  - `text` (required): Message text (max 10,000 characters)
  - `sender_name` (required): Dedicated sender name
  - `attachments` (optional): Array of HTTPS URLs (max 3 items, 256 chars each)
  - `timeout` (optional): Timeout in seconds (min 5 seconds)
  - `passthrough` (optional): Metadata string (max 1000 chars)
  - `status_callback` (optional): Webhook URL (max 256 chars)
  - `status_callback_header` (optional): Custom auth header (max 256 chars)
  - `reply_to_id` (optional): Message ID for replies
  - `subject` (optional): Message subject (bold title)
  - `effect` (optional): Message effect (slam, loud, gentle, etc.)
  - `service` (optional): imessage or sms (default: imessage)

#### 2. Send Group Message
- **Method**: `POST /message/send/`
- **Purpose**: Send message to iMessage group
- **Parameters**:
  - `group` (required): iMessage group ID
  - `text` (required): Message text
  - `sender_name` (required): Dedicated sender name
  - `attachments` (optional): Array of HTTPS URLs
  - `timeout` (optional): Timeout in seconds
  - `passthrough` (optional): Metadata string
  - `status_callback` (optional): Webhook URL
  - `status_callback_header` (optional): Custom auth header

#### 3. Send Audio Message
- **Method**: `POST /message/send/`
- **Purpose**: Send audio file as voice message
- **Parameters**:
  - `recipient` (required): Phone number or email
  - `text` (required): Message text
  - `media_url` (required): HTTPS URL to audio file
  - `sender_name` (required): Dedicated sender name
  - `audio_message` (required): Boolean true
  - `status_callback` (optional): Webhook URL
  - `status_callback_header` (optional): Custom auth header
  - `passthrough` (optional): Metadata string

#### 4. Send Reaction
- **Method**: `POST /message/send/`
- **Purpose**: Send tapback reaction to existing message
- **Parameters**:
  - `recipient` (required): Phone number or email
  - `text` (required): Message text
  - `message_id` (required): Target message ID
  - `sender_name` (required): Dedicated sender name
  - `reaction` (required): Reaction type (love, like, dislike, laugh, exclaim, question, -love, etc.)
  - `status_callback` (optional): Webhook URL
  - `status_callback_header` (optional): Custom auth header
  - `passthrough` (optional): Metadata string

#### 5. Check Message Status
- **Method**: `GET /message/status/{id}/`
- **Purpose**: Check status of sent message by message ID
- **Returns**: Status and message details

### Phone Number Formats
Supports international formats with optional formatting:
- `13231234567`
- `+13231111111`
- `+1 (323) 1111111`
- `+1 323 123 4567`
- `1 (323)-123-4567`

### Message Effects
Available effects: `slam`, `loud`, `gentle`, `invisibleInk`, `echo`, `spotlight`, `balloons`, `confetti`, `love`, `lasers`, `fireworks`, `shootingStar`, `celebration`

### Reaction Types
- **Add**: `love`, `like`, `dislike`, `laugh`, `exclaim`, `question`
- **Remove**: `-love`, `-like`, `-dislike`, `-laugh`, `-exclaim`, `-question`

### Response Statuses
- `processing`: Request accepted and being processed
- `scheduled`: Request processed and scheduled for sending
- `failed`: Failed to send or deliver message
- `sent`: Message successfully delivered to recipient
- `timeout`: Message timed out during sending
- `unknown`: Message status currently unknown

### Error Codes
- `100`: Bad request
- `110`: Missing credentials
- `120`: Missing required parameters
- `125`: Invalid authorization key
- `130`: Invalid secret key
- `140`: No "text" parameter
- `150`: No "recipient" parameter
- `160`: Invalid recipient
- `170`: Invalid recipient email
- `180`: Invalid recipient phone number
- `190`: Phone number is not mobile
- `210`: Sender name not specified
- `220`: Invalid sender name
- `230`: Internal error with sender name
- `240`: Sender name not activated or unpaid
- `270`: Recipient blocked messages
- `300`: Unable to send without dedicated sender name
- `330`: Messages sent too frequently
- `400`: No available requests/credits
- `500`: Account suspended
- `510`: Account blocked
- `530`: Account suspended due to debt
- `540`: No active sender name
- `545`: Sender name suspended by Apple
- `550`: Requires dedicated sender name or sandbox contact
- `560`: Unable to send until recipient initiates conversation
- `570`: API request deprecated
- `580`: Invalid effect parameter
- `590`: Invalid message_id for reply
- `595`: Invalid or non-existent message_id
- `600`: Invalid reaction parameter
- `610`: Reaction or message_id invalid
- `620`: Cannot use effect and reaction in same request
- `630`: Need to set up vCard file
- `640`: No media file URL
- `1110`: Cannot send SMS to email address
- `1120`: Cannot send SMS to group
- `1130`: Cannot send SMS with marketing content
- `1140`: Cannot send audio messages through SMS

## Implementation Plan

### 1. Data Models (`models.py` - Additional Models)

#### Input Models
```python
class LoopMessageSingleInput(BaseModel):
    """Input model for single message sending"""
    recipient: str = Field(..., description="Phone number or email address")
    text: str = Field(..., description="Message text", max_length=10000)
    sender_name: str = Field(..., description="Dedicated sender name")
    attachments: Optional[List[str]] = Field(None, description="Array of HTTPS URLs", max_items=3)
    timeout: Optional[int] = Field(None, description="Timeout in seconds", ge=5)
    passthrough: Optional[str] = Field(None, description="Metadata string", max_length=1000)
    status_callback: Optional[str] = Field(None, description="Webhook URL", max_length=256)
    status_callback_header: Optional[str] = Field(None, description="Custom auth header", max_length=256)
    reply_to_id: Optional[str] = Field(None, description="Message ID for replies")
    subject: Optional[str] = Field(None, description="Message subject")
    effect: Optional[str] = Field(None, description="Message effect")
    service: Optional[str] = Field("imessage", description="Service type: imessage or sms")

class LoopMessageGroupInput(BaseModel):
    """Input model for group message sending"""
    group: str = Field(..., description="iMessage group ID")
    text: str = Field(..., description="Message text", max_length=10000)
    sender_name: str = Field(..., description="Dedicated sender name")
    attachments: Optional[List[str]] = Field(None, description="Array of HTTPS URLs", max_items=3)
    timeout: Optional[int] = Field(None, description="Timeout in seconds", ge=5)
    passthrough: Optional[str] = Field(None, description="Metadata string", max_length=1000)
    status_callback: Optional[str] = Field(None, description="Webhook URL", max_length=256)
    status_callback_header: Optional[str] = Field(None, description="Custom auth header", max_length=256)

class LoopMessageAudioInput(BaseModel):
    """Input model for audio message sending"""
    recipient: str = Field(..., description="Phone number or email address")
    text: str = Field(..., description="Message text", max_length=10000)
    media_url: str = Field(..., description="HTTPS URL to audio file", max_length=256)
    sender_name: str = Field(..., description="Dedicated sender name")
    audio_message: bool = Field(True, description="Must be true for audio messages")
    status_callback: Optional[str] = Field(None, description="Webhook URL", max_length=256)
    status_callback_header: Optional[str] = Field(None, description="Custom auth header", max_length=256)
    passthrough: Optional[str] = Field(None, description="Metadata string", max_length=1000)

class LoopMessageReactionInput(BaseModel):
    """Input model for reaction sending"""
    recipient: str = Field(..., description="Phone number or email address")
    text: str = Field(..., description="Message text", max_length=10000)
    message_id: str = Field(..., description="Target message ID")
    sender_name: str = Field(..., description="Dedicated sender name")
    reaction: str = Field(..., description="Reaction type")
    status_callback: Optional[str] = Field(None, description="Webhook URL", max_length=256)
    status_callback_header: Optional[str] = Field(None, description="Custom auth header", max_length=256)
    passthrough: Optional[str] = Field(None, description="Metadata string", max_length=1000)

class LoopMessageStatusInput(BaseModel):
    """Input model for status check"""
    message_id: str = Field(..., description="Message ID to check status for")
```

#### Output Models
```python
class LoopMessageGroup(BaseModel):
    """Group information"""
    group_id: str = Field(..., description="Group identifier")
    name: Optional[str] = Field(None, description="Group name")
    participants: List[str] = Field(..., description="List of participant phone numbers/emails")

class LoopMessageSingleOutput(BaseModel):
    """Output model for single message"""
    tool: Literal["loop_message_tool"] = Field(..., description="Tool identifier")
    success: bool = Field(..., description="Request success status")
    message_id: str = Field(..., description="Message identifier")
    recipient: str = Field(..., description="Normalized recipient")
    text: str = Field(..., description="Message text")

class LoopMessageGroupOutput(BaseModel):
    """Output model for group message"""
    tool: Literal["loop_message_tool"] = Field(..., description="Tool identifier")
    success: bool = Field(..., description="Request success status")
    message_id: str = Field(..., description="Message identifier")
    group: LoopMessageGroup = Field(..., description="Group information")
    text: str = Field(..., description="Message text")

class LoopMessageStatusResult(BaseModel):
    """Message status result"""
    message_id: str = Field(..., description="Message identifier")
    status: str = Field(..., description="Message status")
    recipient: Optional[str] = Field(None, description="Recipient")
    text: Optional[str] = Field(None, description="Message text")
    sandbox: Optional[bool] = Field(None, description="Sandbox status")
    error_code: Optional[int] = Field(None, description="Error code if failed")
    sender_name: Optional[str] = Field(None, description="Sender name")
    passthrough: Optional[str] = Field(None, description="Passthrough metadata")
    last_update: Optional[str] = Field(None, description="Last update timestamp")

class LoopMessageStatusOutput(BaseModel):
    """Output model for status check"""
    tool: Literal["loop_message_tool"] = Field(..., description="Tool identifier")
    result: LoopMessageStatusResult = Field(..., description="Status result")
```

### 2. Tool Implementation (`send_loop_message_tool.py`)

#### Core Features
- **Single Message Sending**: Send text messages with attachments to individuals
- **Group Message Sending**: Send messages to iMessage groups
- **Audio Message Sending**: Send voice/audio messages
- **Reaction Sending**: Send tapback reactions to existing messages
- **Status Checking**: Check message delivery status
- **Error Handling**: Comprehensive error handling with Loop Message-specific error codes
- **Attachment Support**: Support for image attachments via HTTPS URLs
- **Message Effects**: Support for iMessage effects and subjects
- **Service Selection**: Choose between iMessage and SMS delivery

#### Key Methods
```python
class LoopMessageTool(AbstractTool):
    def __init__(self, config: dict):
        super().__init__(config)
        self.authorization_key = config.get('authorization_key')
        self.secret_key = config.get('secret_key')
        self.base_url = "https://server.loopmessage.com/api/v1"
        
    def handle_tool_request(self, tool_request: ToolRequest) -> ToolResponse:
        # Route to appropriate method based on input type
        
    def _send_single_message(self, validated_input) -> dict:
        # Handle single message sending
        
    def _send_group_message(self, validated_input) -> dict:
        # Handle group message sending
        
    def _send_audio_message(self, validated_input) -> dict:
        # Handle audio message sending
        
    def _send_reaction(self, validated_input) -> dict:
        # Handle reaction sending
        
    def _check_status(self, validated_input) -> dict:
        # Handle status checking
        
    def _make_api_request(self, method: str, endpoint: str, data: dict = None) -> dict:
        # Common API request handler with dual authentication
```

### 3. Configuration Setup

#### Update `app_config.yaml.template`
```yaml
vital_agent_resource_app:
  tools:
    - tool_id: "loop_message_tool"
      authorization_key: "your_loop_message_authorization_key_here"
      secret_key: "your_loop_message_secret_key_here"
    # ... existing tools
```

#### Update `ToolName` enum
```python
class ToolName(str, Enum):
    # ... existing tools
    loop_message_tool = "loop_message_tool"
```

#### Register in `app.py`
```python
# Import models and tool
from vital_agent_resource_app.tools.send_message.models import (
    LoopMessageSingleInput, LoopMessageGroupInput, LoopMessageAudioInput,
    LoopMessageReactionInput, LoopMessageStatusInput,
    LoopMessageSingleOutput, LoopMessageGroupOutput, LoopMessageStatusOutput
)
from vital_agent_resource_app.tools.send_message.send_loop_message_tool import LoopMessageTool

# Get configuration
loop_message_config = get_tool_by_id(config, 'loop_message_tool')

# Register tool
tool_registry.add_tool(
    tool_name=ToolName.loop_message_tool.value,
    input_model=Union[LoopMessageSingleInput, LoopMessageGroupInput, LoopMessageAudioInput, LoopMessageReactionInput, LoopMessageStatusInput],
    output_model=Union[LoopMessageSingleOutput, LoopMessageGroupOutput, LoopMessageStatusOutput],
    tool_instance=LoopMessageTool(loop_message_config)
)
```

### 4. Security Considerations

- **Dual Authentication**: Store both authorization key and secret key securely
- **Input Validation**: Validate phone numbers, emails, URLs, and text length
- **URL Validation**: Ensure attachment URLs are HTTPS and publicly accessible
- **Rate Limiting**: Respect API rate limits and FIFO queue behavior
- **Error Handling**: Don't expose sensitive error details to end users
- **HTTPS Only**: Ensure all requests use HTTPS with proper TLS

### 5. Usage Examples

#### Single Message
```json
{
    "tool": "loop_message_tool",
    "tool_input": {
        "recipient": "+1 (323) 123-4567",
        "text": "Hello from Loop Message!",
        "sender_name": "MyApp",
        "attachments": ["https://example.com/image.jpg"],
        "effect": "balloons"
    }
}
```

#### Group Message
```json
{
    "tool": "loop_message_tool",
    "tool_input": {
        "group": "2BC4FD6A-CE49-439F-81DF-E895C09CA49C",
        "text": "Hello group!",
        "sender_name": "MyApp"
    }
}
```

#### Audio Message
```json
{
    "tool": "loop_message_tool",
    "tool_input": {
        "recipient": "+1 (323) 123-4567",
        "text": "Voice message",
        "media_url": "https://example.com/audio.mp3",
        "sender_name": "MyApp",
        "audio_message": true
    }
}
```

#### Reaction
```json
{
    "tool": "loop_message_tool",
    "tool_input": {
        "recipient": "+1 (323) 123-4567",
        "text": "Reaction",
        "message_id": "2BC4FD6A-CE49-439F-81DF-E895C09CA49C",
        "sender_name": "MyApp",
        "reaction": "love"
    }
}
```

#### Status Check
```json
{
    "tool": "loop_message_tool",
    "tool_input": {
        "message_id": "2BC4FD6A-CE49-439F-81DF-E895C09CA49C"
    }
}
```

### 6. Testing Strategy

- **Unit Tests**: Test individual methods and error handling
- **Integration Tests**: Test API integration with mock responses
- **Validation Tests**: Test phone number, email, and URL validation
- **Error Handling Tests**: Test all error codes and scenarios
- **Message Type Tests**: Test all message types (single, group, audio, reaction)
- **Configuration Tests**: Test tool registration and configuration

### 7. Dependencies

Required Python packages (likely already available):
- `requests`: For HTTP API calls
- `pydantic`: For data validation (already in use)
- `typing`: For type hints (built-in)

### 8. Implementation Priority

1. **High Priority**:
   - Create data models for all message types
   - Implement core `LoopMessageTool` class
   - Add single message sending functionality
   - Basic error handling and validation

2. **Medium Priority**:
   - Add group message functionality
   - Implement audio message sending
   - Add reaction sending capability
   - Implement status checking
   - Update configuration files
   - Register tool in application

3. **Low Priority**:
   - Advanced error handling
   - Comprehensive testing
   - Documentation updates
   - Performance optimizations
   - Webhook integration support

### 9. Future Enhancements

- **Webhook Support**: Implement webhook handling for message status updates
- **Message Templates**: Create reusable message templates
- **Bulk Messaging**: Implement bulk message sending capabilities
- **Media Validation**: Validate media files before sending
- **Retry Logic**: Implement exponential backoff for failed requests
- **Analytics**: Track message delivery rates and performance
- **Caching**: Cache sender names and group information

## Next Steps

1. Start with implementing the data models in `models.py`
2. Create the basic `LoopMessageTool` class structure
3. Implement single message sending first
4. Add configuration and registration
5. Test with single messages before expanding to other message types
6. Gradually add group, audio, and reaction message capabilities
7. Implement status checking functionality

This implementation will follow the established patterns in the codebase and provide a robust integration with the Loop Message API service for comprehensive iMessage and SMS messaging capabilities.