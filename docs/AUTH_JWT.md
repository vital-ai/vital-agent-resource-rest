# JWT Authentication Implementation Plan

## Overview
This document outlines the implementation plan for adding JWT (JSON Web Token) authentication to the existing Vital Agent Resource REST API endpoints. The authentication system will secure tool endpoints and LLM endpoints using industry-standard JWT validation.

## Current State Analysis

### Existing Endpoints Requiring Authentication
- `POST /tool` - Tool execution endpoint (currently unprotected)
- `POST /v1/completions` - LLM completion endpoint (currently unprotected)

### Public Endpoints (No Authentication Required)
- `GET /health` - Health check endpoint (remains public)


## Implementation Plan

### Phase 1: Analysis and Design (High Priority)

#### 1. Endpoint Analysis and Permission Model Design
- **Status**: ✅ Completed
- **Tasks**:
  - ✅ Mapped existing endpoints to authentication requirements
  - ✅ Simplified to binary authentication (authenticated vs unauthenticated)
  - ✅ Designed JWT token payload structure
  - ✅ Planned authentication flow

#### 2. JWT Authentication Flow Design  
- **Status**: ✅ Completed
- **Tasks**:
  - ✅ Designed token validation process
  - ✅ Implemented user extraction from JWT payload
  - ✅ Defined error handling for authentication failures
  - ✅ Implemented development mode (JWT disabled) support

### Phase 2: Core Infrastructure (High Priority)

#### 3. JWT Utilities Module
- **Status**: ✅ Completed
- **File**: `vital_agent_resource_app/auth/jwt_utils.py`
- **Tasks**:
  - ✅ Created `JWTUtils` class with token validation
  - ✅ Support RS256 (RSA) and HS256 (HMAC) algorithms
  - ✅ Implemented user ID and permission extraction
  - ✅ Created custom exceptions (`JWTValidationError`, `JWTExpiredError`, `JWTInvalidClaimsError`)

#### 4. Authentication Models
- **Status**: ✅ Completed  
- **File**: `vital_agent_resource_app/data_models/auth_models.py`
- **Tasks**:
  - ✅ Created `AuthenticatedUser` model with permission checking methods
  - ✅ Created `JWTConfig` model for configuration validation
  - ✅ Created error response models

#### 5. FastAPI Dependencies
- **Status**: ✅ Completed
- **File**: `vital_agent_resource_app/auth/dependencies.py`
- **Tasks**:
  - ✅ Created `get_current_user_dependency()` main authentication function
  - ✅ Simplified to single authentication dependency (no role/permission checking)
  - ✅ Reads configuration from environment variables

### Phase 3: Configuration and Setup (Medium Priority)

#### 6. Environment Configuration
- **Status**: ✅ Completed
- **File**: `.env.example`
- **Tasks**:
  - ✅ Added JWT configuration to environment variables
  - ✅ Included all necessary JWT settings
  - ✅ Set secure defaults

#### 7. Dependency Management
- **Status**: ✅ Completed
- **File**: `requirements.txt`
- **Tasks**:
  - ✅ Added `PyJWT>=2.8.0` dependency

### Phase 4: Endpoint Protection (Medium Priority)

#### 8. Apply Authentication to Tool Endpoint
- **Status**: ✅ Completed
- **Target**: `POST /tool` endpoint in `app.py`
- **Implementation**:
```python
@app.post("/tool", response_model=ToolResponse, tags=["Tools"])
async def handle_tool_request(
    request: ToolRequest,
    current_user: AuthenticatedUser = Depends(get_current_user_dependency)
):
```

#### 9. Apply Authentication to LLM Completions
- **Status**: ✅ Completed  
- **Target**: `POST /v1/completions` endpoint in `app.py`
- **Implementation**:
```python
@app.post("/v1/completions")
async def handle_completions_request(
    raw_request: Request,
    current_user: AuthenticatedUser = Depends(get_current_user_dependency)
):
```

### Phase 5: Advanced Features (Medium Priority)

#### 10. JWT Middleware Implementation
- **Status**: ✅ Completed
- **File**: `vital_agent_resource_app/auth/middleware.py`
- **Tasks**:
  - ✅ Created global JWT authentication middleware
  - ✅ Added request logging with user context
  - ✅ Implemented performance monitoring

### Phase 6: Testing and Documentation (Low Priority)

#### 11. Test Suite Creation
- **Status**: ✅ Completed
- **File**: `tests/jwt_auth_test.py`
- **Tasks**:
  - ✅ Unit tests for JWT validation logic
  - ✅ Authentication flow integration tests
  - ✅ Permission and role checking tests
  - ✅ Error handling tests

#### 12. Documentation Updates
- **Status**: ✅ Completed
- **Tasks**:
  - ✅ Updated configuration examples
  - ✅ Documented usage patterns
  - ✅ Added security considerations
  - ✅ Updated implementation plan

## JWT Token Structure

### Expected JWT Payload
```json
{
  "sub": "user123",
  "exp": 1640995200,
  "iat": 1640991600,
  "iss": "vital-ai",
  "aud": "vital-agent-resource",
  "permissions": ["tool:execute", "llm:complete"],
  "roles": ["user"],
  "user_id": "user123",
  "email": "user@example.com"
}
```

### Authentication Model
- **Binary Authentication**: Users are either authenticated or not (no role/permission checking)
- **Protected Endpoints**: Require valid JWT token in Authorization header
- **Public Endpoints**: No authentication required
- **Development Mode**: JWT disabled, default user injected for testing

## Configuration Structure

JWT configuration is now managed through environment variables for security:

```bash
# JWT Authentication Configuration
JWT_ENABLED=false                                    # Enable/disable JWT authentication
JWT_ALGORITHM=RS256                                  # RS256 (RSA) or HS256 (HMAC)
JWT_SECRET_KEY=your-secret-key-for-hmac-algorithms  # Required for HMAC algorithms
JWT_PUBLIC_KEY_PATH=/path/to/jwt_public.pem         # Required for RSA algorithms (if no JWKS URL)
JWT_JWKS_URL=https://your-auth-provider.com/.well-known/jwks.json  # JWKS URL for RSA key discovery
JWT_REQUIRED_CLAIMS=sub,exp,iat                     # Required JWT claims (comma-separated)
JWT_TOKEN_EXPIRY_SECONDS=3600                       # Token expiry time in seconds
JWT_ISSUER=vital-ai                                 # Expected JWT issuer
JWT_AUDIENCE=vital-agent-resource                   # Expected JWT audience
```

### Configuration Notes
- Set `JWT_ENABLED=true` to enable authentication in production
- Use `JWT_ALGORITHM=RS256` with public/private key pairs for production
- Use `JWT_ALGORITHM=HS256` with shared secret for development/testing
- **JWKS URL Support**: For RSA algorithms, you can use either:
  - `JWT_JWKS_URL`: Automatically fetch public keys from JWKS endpoint (recommended for production)
  - `JWT_PUBLIC_KEY_PATH`: Use a local public key file (fallback option)
- JWKS URL takes priority over public key file if both are configured
- JWT tokens must include `kid` (Key ID) in header when using JWKS URL
- Keep sensitive keys in environment variables, never in code

## Implementation Priority

1. **Critical Path**: Phase 1-2 (Analysis, JWT utilities, models, dependencies)
2. **Core Features**: Phase 3-4 (Configuration, endpoint protection)
3. **Enhancement**: Phase 5-6 (Middleware, testing, documentation)

## Security Considerations

1. **Development Mode**: JWT disabled by default for local development
2. **Key Management**: Secure storage and rotation of JWT keys
3. **Token Expiry**: Implement reasonable expiration times
4. **Error Handling**: Avoid exposing sensitive information in error responses
5. **HTTPS Only**: Enforce HTTPS in production environments
6. **Rate Limiting**: Consider implementing rate limiting on authentication endpoints

## Success Criteria

- ✅ All existing endpoints protected with appropriate JWT authentication
- ✅ Simplified binary authentication model (no roles/permissions)
- ✅ Development mode support for local testing
- ✅ Comprehensive test coverage
- ✅ Clear documentation and configuration examples
- ✅ No breaking changes to existing API contracts (when JWT disabled)
- ✅ Environment variable configuration for security

## Endpoint Authentication Requirements

### Public Endpoints (No Authentication)
- `GET /health` - Health check endpoint

### Protected Endpoints (JWT Required)
- `POST /tool` - Tool execution endpoint
- `POST /v1/completions` - LLM completion endpoint

## Usage Examples

### Protected Endpoint Implementation
```python
@router.post("/tool", response_model=ToolResponse, tags=["Tools"])
async def handle_tool_request(
    request: ToolRequest,
    current_user: AuthenticatedUser = Depends(get_current_user_dependency)
):
    """Execute tool with authenticated user context."""
    # Tool execution logic with user context
    pass
```

### Authentication Header Format
```bash
Authorization: Bearer <jwt_token>
```

### JWT Token Format
```json
{
  "sub": "user123",
  "exp": 1640995200,
  "iat": 1640991600,
  "iss": "vital-ai",
  "aud": "vital-agent-resource",
  "permissions": ["tool:execute", "llm:complete"],
  "user_id": "user123",
  "email": "user@example.com"
}
```

## Error Handling

### Authentication Errors
- `401 Unauthorized`: Missing or invalid JWT token
- `403 Forbidden`: Valid token but insufficient permissions
- `422 Unprocessable Entity`: Malformed token or missing claims

### Error Response Format
```json
{
  "error": "authentication_failed",
  "message": "JWT token has expired",
  "details": {
    "error_type": "JWTExpiredError",
    "timestamp": "2024-01-15T10:30:00Z"
  }
}
```

## Security Considerations

1. **Token Storage**: Tokens should be stored securely on the client side
2. **HTTPS Only**: All authentication must occur over HTTPS in production
3. **Token Expiry**: Implement reasonable token expiry times
4. **Key Rotation**: Support for key rotation without service interruption
5. **Rate Limiting**: Implement rate limiting on authentication endpoints
6. **Audit Logging**: Log all authentication attempts and failures

## Testing Strategy

1. **Unit Tests**: Test JWT validation logic and user extraction
2. **Integration Tests**: Test endpoint authentication with various token scenarios
3. **Security Tests**: Test with malformed, expired, and invalid tokens
4. **Performance Tests**: Ensure authentication doesn't significantly impact response times

## Deployment Considerations

1. **Environment Variables**: Use environment variables for sensitive configuration
2. **Key Management**: Secure storage and distribution of JWT keys
3. **Monitoring**: Monitor authentication success/failure rates
4. **Graceful Degradation**: Handle authentication service outages appropriately