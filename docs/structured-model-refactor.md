# Structured Model Refactor

## Overview
Refactoring the tool system to use structured Pydantic models for FastAPI documentation and type safety.

## Current Architecture
- **Tool Endpoint**: Single `/tool` endpoint using raw `Request` and manual JSON parsing
- **ToolRequest**: Simple wrapper class around dictionary
- **ToolResponse**: Simple wrapper class around dictionary
- **FastAPI Docs**: Shows generic request body without structure

## Target Architecture - 4-Layer Model Structure

### Layer 1: Top-Level Request/Response Models
```python
class ToolRequest(BaseModel):
    # Non-tool-specific parameters
    request_id: Optional[str] = Field(None, description="Optional request identifier")
    timeout: Optional[int] = Field(None, description="Request timeout in seconds")
    # Tool-specific input
    tool_input: ToolInput = Field(..., description="Tool-specific input parameters")

class ToolResponse(BaseModel):
    # Non-tool-specific parameters  
    duration_ms: int = Field(..., description="Tool execution duration in milliseconds")
    success: bool = Field(..., description="Whether the tool execution was successful")
    error_message: Optional[str] = Field(None, description="Error message if execution failed")
    # Tool-specific output
    tool_output: ToolOutput = Field(..., description="Tool-specific output data")
```

### Layer 2: Tool Input/Output Union Types
```python
# Union of all tool-specific input models (dynamically registered)
ToolInput = Union[AddressValidationInput, PlaceSearchInput, WeatherInput, ...]

# Union of all tool-specific output models (dynamically registered)  
ToolOutput = Union[AddressValidationOutput, PlaceSearchOutput, WeatherOutput, ...]
```

### Layer 3: Tool-Specific Top-Level Models
```python
# Address Validation Tool
class AddressValidationInput(BaseModel):
    tool: Literal["google_address_validation_tool"]
    address: str = Field(..., description="Address to validate")

class AddressValidationOutput(BaseModel):
    tool: Literal["google_address_validation_tool"]
    results: List[AddressValidationResult]

# Place Search Tool
class PlaceSearchInput(BaseModel):
    tool: Literal["place_search_tool"]
    place_search_string: str = Field(..., description="Search query")

class PlaceSearchOutput(BaseModel):
    tool: Literal["place_search_tool"]
    results: List[PlaceDetails]
```

### Layer 4: Tool-Specific Data Models
```python
# Address Validation specific data structures
class AddressValidationResult(BaseModel):
    formatted_address: str
    postal_address: Dict[str, Any]
    address_components: List[AddressComponent]
    # ... other fields

# Place Search specific data structures
class PlaceDetails(BaseModel):
    name: str
    address: str
    place_id: str
    # ... other fields
```

## Challenge: Union vs Alternatives

### Problem
With 100+ tools, using Union types becomes unwieldy:
```python
tool_parameters: Union[AddressValidationParams, PlaceSearchParams, ..., Tool100Params]
```

### Dynamic Model Registration (Selected Approach)

```python
class ToolRegistry:
    _input_models = {}
    _output_models = {}
    
    @classmethod
    def register_tool(cls, tool_name: str, input_model: Type[BaseModel], output_model: Type[BaseModel]):
        cls._input_models[tool_name] = input_model
        cls._output_models[tool_name] = output_model
    
    @classmethod
    def get_input_model(cls, tool_name: str) -> Type[BaseModel]:
        return cls._input_models.get(tool_name)
    
    @classmethod
    def get_output_model(cls, tool_name: str) -> Type[BaseModel]:
        return cls._output_models.get(tool_name)
    
    @classmethod
    def get_tool_input_union(cls):
        """Generate Union type for all registered tool inputs"""
        return Union[tuple(cls._input_models.values())]
    
    @classmethod
    def get_tool_output_union(cls):
        """Generate Union type for all registered tool outputs"""
        return Union[tuple(cls._output_models.values())]

# Usage in tool modules
ToolRegistry.register_tool(
    "google_address_validation_tool",
    AddressValidationInput,
    AddressValidationOutput
)
```

#### Option 2: Generic with Discriminator
```python
class ToolRequest(BaseModel):
    tool: str = Field(..., description="Tool identifier")
    tool_parameters: Dict[str, Any] = Field(..., description="Tool-specific parameters")
    
    class Config:
        # Use discriminator field for documentation
        discriminator = 'tool'
```

#### Option 3: Plugin-Style Model Discovery
```python
# Each tool module exports its models
def get_tool_models():
    return {
        "google_address_validation_tool": {
            "params": AddressValidationParams,
            "response": AddressValidationResult
        }
    }
```

#### Option 4: Annotation-Based Registration
```python
@tool_model("google_address_validation_tool")
class AddressValidationParams(BaseModel):
    address: str

@tool_response("google_address_validation_tool") 
class AddressValidationResult(BaseModel):
    formatted_address: str
```

## Implementation Plan

### Phase 1: Base Model Conversion
- [ ] Convert `ToolRequest` to Pydantic model
- [ ] Convert `ToolResponse` to Pydantic model
- [ ] Update endpoint to use Pydantic models
- [ ] Maintain backward compatibility

### Phase 2: Tool-Specific Models
- [ ] Define models for existing tools:
  - [ ] Google Address Validation
  - [ ] Place Search
  - [ ] Weather
  - [ ] Amazon Product Search
  - [ ] Google Web Search
- [ ] Implement chosen approach for model registration/discovery

### Phase 3: Documentation Enhancement
- [ ] Add rich examples to models
- [ ] Generate comprehensive FastAPI docs
- [ ] Test documentation completeness

### Phase 4: Validation & Error Handling
- [ ] Add proper validation error responses
- [ ] Enhance error messages for tool-specific validation
- [ ] Test edge cases

## Questions to Resolve
1. Which approach for handling 100+ tool models?
2. How to maintain backward compatibility during transition?
3. Should we validate tool parameters at the endpoint level or tool level?
4. How to handle optional vs required parameters across different tools?

## Benefits
- **Rich FastAPI Documentation**: Each tool's parameters clearly documented
- **Type Safety**: Compile-time validation of tool parameters
- **Better Error Messages**: Specific validation errors for each tool
- **IDE Support**: Autocomplete and type hints for tool development
- **API Consistency**: Standardized request/response structure
