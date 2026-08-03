# Loop Lookup Tool Implementation Plan

## Overview
Implementation plan for integrating the Loop Lookup API into the Vital Agent Resource REST system. The Loop Lookup API provides phone number and email validation services to check if contacts are reachable via iMessage.

## API Analysis

### Base URL
- Production: `https://a.looplookup.com/api/v1/`

### Authentication
- **Header**: `Authorization: {API_KEY}` (no Bearer prefix required)
- **Content-Type**: `application/json`
- **Protocol**: HTTPS only (minimum TLS v1.2)
- **Supported Ports**: 443, 2053, 2083, 2087, 2096, 8443

### Endpoints

#### 1. Single Lookup Request
- **Method**: `POST /lookup/`
- **Purpose**: Submit single contact for iMessage reachability check
- **Parameters**:
  - `contact` (required): Phone number or email
  - `region` (optional): ISO-2 country code (US, GB, CA, AU, etc.)
  - `contact_details` (optional): Boolean for additional phone info (carrier, type, timezone)

#### 2. Bulk Lookup Request  
- **Method**: `POST /lookup/`
- **Purpose**: Submit multiple contacts for batch processing
- **Parameters**:
  - `contacts` (required): Array of phone numbers/emails
  - `region` (optional): ISO-2 country code
  - `contact_details` (optional): Boolean for additional phone info
- **Limits**: Max 2-3k contacts per request (30-second timeout)

#### 3. Status Check
- **Method**: `GET /lookup/status/{id}/`
- **Purpose**: Check lookup request status by request ID
- **Returns**: Status and results when available

#### 4. Cancel Bulk Request
- **Method**: `DELETE /bulk-lookup/delete/{id}/`
- **Purpose**: Cancel pending bulk lookup request

### Phone Number Formats
Supports international formats with optional formatting:
- `13231234567`
- `+13231111111`
- `+1 (323) 1111111`
- `+1 323 123 4567`
- `1 (323)-123-4567`

### Response Statuses
- `queued`: Request accepted and queued
- `processing`: Request being processed
- `completed`: Request completed with results
- `canceled`: Request canceled by user

### Error Codes
- `100`: Bad request
- `110`: Missing credentials
- `120`: Missing required parameters
- `125`: Invalid authorization key
- `130`: Invalid secret key
- `150`: Missing recipient parameter
- `160`: Invalid recipient
- `170`: Invalid recipient email
- `180`: Invalid recipient phone number
- `190`: Phone number is not mobile
- `400`: No available requests/credits
- `500`: Account suspended
- `510`: Account blocked
- `530`: Account suspended due to debt

## Implementation Plan

### 1. Data Models (`models.py`)

#### Input Models
```python
class LoopLookupSingleInput(BaseModel):
    """Input model for single contact lookup"""
    contact: str = Field(..., description="Phone number or email address")
    region: Optional[str] = Field(None, description="ISO-2 country code (US, GB, CA, etc.)")
    contact_details: Optional[bool] = Field(False, description="Include additional contact information")

class LoopLookupBulkInput(BaseModel):
    """Input model for bulk contact lookup"""
    contacts: List[str] = Field(..., description="Array of phone numbers or email addresses", max_items=3000)
    region: Optional[str] = Field(None, description="ISO-2 country code (US, GB, CA, etc.)")
    contact_details: Optional[bool] = Field(False, description="Include additional contact information")

class LoopLookupStatusInput(BaseModel):
    """Input model for status check"""
    request_id: str = Field(..., description="Request ID to check status for")
```

#### Output Models
```python
class LoopLookupRequest(BaseModel):
    """Individual lookup request result"""
    contact: str = Field(..., description="Normalized contact (phone/email)")
    request_id: str = Field(..., description="Unique request identifier")

class AppleServiceLinks(BaseModel):
    """Apple service deep links"""
    facetime_audio: Optional[str] = Field(None, description="FaceTime audio deep link")
    facetime: Optional[str] = Field(None, description="FaceTime video deep link")
    tel: Optional[str] = Field(None, description="Phone call deep link")
    imessage: Optional[str] = Field(None, description="iMessage deep link")
    sms: Optional[str] = Field(None, description="SMS deep link")

class AppleServiceStatus(BaseModel):
    """Apple service availability status"""
    status: str = Field(..., description="Service status: available, unavailable, unknown")
    date: Optional[str] = Field(None, description="Last known date of data (YYYY-MM-DD)")
    links: Optional[AppleServiceLinks] = Field(None, description="Deep links for the service")

class AppleServices(BaseModel):
    """Apple services availability"""
    facetime: Optional[AppleServiceStatus] = Field(None, description="FaceTime availability")
    imessage: Optional[AppleServiceStatus] = Field(None, description="iMessage availability")

class CarrierInfo(BaseModel):
    """Carrier information"""
    carrier: Optional[str] = Field(None, description="Carrier name (e.g., Verizon)")
    number_type: Optional[str] = Field(None, description="Number type: mobile, fixed_line, fixed_line_or_mobile")

class CountryInfo(BaseModel):
    """Country information"""
    flag: Optional[str] = Field(None, description="Country flag emoji")
    iso2: Optional[str] = Field(None, description="ISO2 country code")
    iso3: Optional[str] = Field(None, description="ISO3 country code")
    name: Optional[str] = Field(None, description="Country name")
    description: Optional[str] = Field(None, description="Region/state description")
    numeric: Optional[int] = Field(None, description="Numeric country code")

class PhoneFormat(BaseModel):
    """Phone number formatting"""
    e164: Optional[str] = Field(None, description="E164 format (+13231112233)")
    international: Optional[str] = Field(None, description="International format (+1 323-111-2233)")
    national: Optional[str] = Field(None, description="National format ((323) 111-2233)")
    out_of_usa: Optional[str] = Field(None, description="Out of USA format (1 (323) 111-2233)")
    rfc3966: Optional[str] = Field(None, description="RFC3966 format (tel:+1-323-111-2233)")

class LookupResultData(BaseModel):
    """Structured lookup result data based on official API documentation"""
    apple_services: Optional[AppleServices] = Field(None, description="Apple services availability")
    carrier: Optional[CarrierInfo] = Field(None, description="Carrier information")
    country: Optional[CountryInfo] = Field(None, description="Country information")
    currencies: Optional[List[str]] = Field(None, description="Supported currencies")
    format: Optional[PhoneFormat] = Field(None, description="Phone number formats")
    time_zones: Optional[List[str]] = Field(None, description="Time zones")

class LoopLookupResult(BaseModel):
    """Lookup result data"""
    request_id: str = Field(..., description="Request identifier")
    status: str = Field(..., description="Request status (queued, processing, completed, canceled)")
    contact: Optional[str] = Field(None, description="Contact that was looked up")
    result_v1: Optional[LookupResultData] = Field(None, description="Structured lookup results when completed")

class LoopLookupSingleOutput(BaseModel):
    """Output model for single lookup"""
    tool: Literal["loop_lookup_tool"] = Field(..., description="Tool identifier")
    success: bool = Field(..., description="Request success status")
    request: LoopLookupRequest = Field(..., description="Request details")

class LoopLookupBulkOutput(BaseModel):
    """Output model for bulk lookup"""
    tool: Literal["loop_lookup_tool"] = Field(..., description="Tool identifier")
    success: bool = Field(..., description="Request success status")
    requests: List[LoopLookupRequest] = Field(..., description="List of request details")

class LoopLookupStatusOutput(BaseModel):
    """Output model for status check"""
    tool: Literal["loop_lookup_tool"] = Field(..., description="Tool identifier")
    result: LoopLookupResult = Field(..., description="Status and result data")
```

### 2. Tool Implementation (`loop_lookup_tool.py`)

#### Core Features
- **Single Contact Lookup**: Submit individual phone/email for validation
- **Bulk Contact Lookup**: Submit up to 3000 contacts in batches
- **Status Checking**: Check request status and retrieve results
- **Error Handling**: Comprehensive error handling with specific error codes
- **Phone Number Validation**: Support for various international formats
- **Configuration**: API key and endpoint configuration via YAML

#### Key Methods
```python
class LoopLookupTool(AbstractTool):
    def __init__(self, config: dict):
        super().__init__(config)
        self.api_key = config.get('api_key')
        self.base_url = "https://a.looplookup.com/api/v1"
        
    def handle_tool_request(self, tool_request: ToolRequest) -> ToolResponse:
        # Route to appropriate method based on input type
        
    def _single_lookup(self, validated_input) -> dict:
        # Handle single contact lookup
        
    def _bulk_lookup(self, validated_input) -> dict:
        # Handle bulk contact lookup
        
    def _status_check(self, validated_input) -> dict:
        # Handle status checking
        
    def _make_api_request(self, method: str, endpoint: str, data: dict = None) -> dict:
        # Common API request handler with authentication
```

### 3. Configuration Setup

#### Update `app_config.yaml.template`
```yaml
vital_agent_resource_app:
  tools:
    - tool_id: "loop_lookup_tool"
      api_key: "your_loop_lookup_api_key_here"
    # ... existing tools
```

#### Update `ToolName` enum
```python
class ToolName(str, Enum):
    # ... existing tools
    loop_lookup_tool = "loop_lookup_tool"
```

#### Register in `app.py`
```python
# Import models and tool
from vital_agent_resource_app.tools.send_message.models import (
    LoopLookupSingleInput, LoopLookupBulkInput, LoopLookupStatusInput,
    LoopLookupSingleOutput, LoopLookupBulkOutput, LoopLookupStatusOutput
)
from vital_agent_resource_app.tools.send_message.loop_lookup_tool import LoopLookupTool

# Get configuration
loop_lookup_config = get_tool_by_id(config, 'loop_lookup_tool')

# Register tool
tool_registry.add_tool(
    tool_name=ToolName.loop_lookup_tool.value,
    input_model=Union[LoopLookupSingleInput, LoopLookupBulkInput, LoopLookupStatusInput],
    output_model=Union[LoopLookupSingleOutput, LoopLookupBulkOutput, LoopLookupStatusOutput],
    tool_instance=LoopLookupTool(loop_lookup_config)
)
```

### 4. Security Considerations

- **API Key Protection**: Store API key securely in configuration
- **Input Validation**: Validate phone numbers and email formats
- **Rate Limiting**: Respect API rate limits and batch size restrictions
- **Error Handling**: Don't expose sensitive error details to end users
- **HTTPS Only**: Ensure all requests use HTTPS with proper TLS

### 5. Usage Examples

#### Single Contact Lookup
```json
{
    "tool": "loop_lookup_tool",
    "tool_input": {
        "contact": "+1 (323) 123-4567",
        "region": "US",
        "contact_details": true
    }
}
```

#### Bulk Contact Lookup
```json
{
    "tool": "loop_lookup_tool", 
    "tool_input": {
        "contacts": ["+13231112233", "steve@mac.com", "1(787)111-22-33"],
        "region": "US",
        "contact_details": false
    }
}
```

#### Status Check
```json
{
    "tool": "loop_lookup_tool",
    "tool_input": {
        "request_id": "2BC4FD6A-CE49-439F-81DF-E895C09CA49C"
    }
}
```

### 6. Testing Strategy

- **Unit Tests**: Test individual methods and error handling
- **Integration Tests**: Test API integration with mock responses
- **Validation Tests**: Test phone number and email validation
- **Error Handling Tests**: Test all error codes and scenarios
- **Configuration Tests**: Test tool registration and configuration

### 7. Dependencies

Required Python packages (likely already available):
- `requests`: For HTTP API calls
- `pydantic`: For data validation (already in use)
- `typing`: For type hints (built-in)

### 8. Implementation Priority

1. **High Priority**:
   - Create data models in `models.py`
   - Implement core `LoopLookupTool` class
   - Add single contact lookup functionality
   - Basic error handling and validation

2. **Medium Priority**:
   - Add bulk lookup functionality
   - Implement status checking
   - Update configuration files
   - Register tool in application

3. **Low Priority**:
   - Advanced error handling
   - Comprehensive testing
   - Documentation updates
   - Performance optimizations

### 9. Future Enhancements

- **Webhook Support**: Implement callback handling for async results
- **Caching**: Cache lookup results to reduce API calls
- **Batch Optimization**: Intelligent batching for large contact lists
- **Analytics**: Track usage and success rates
- **Retry Logic**: Implement exponential backoff for failed requests

## Next Steps

1. Start with implementing the data models in `models.py`
2. Create the basic `LoopLookupTool` class structure
3. Implement single contact lookup first
4. Add configuration and registration
5. Test with single contact before expanding to bulk operations
6. Gradually add bulk lookup and status checking features

This implementation will follow the established patterns in the codebase and provide a robust integration with the Loop Lookup API service.