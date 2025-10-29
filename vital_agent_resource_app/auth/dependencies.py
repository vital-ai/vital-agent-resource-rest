import os
import logging
from typing import Optional, List
from datetime import datetime, timezone
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from vital_agent_resource_app.auth.jwt_utils import JWTUtils, JWTValidationError, JWTExpiredError, JWTInvalidClaimsError
from vital_agent_resource_app.data_models.auth_models import AuthenticatedUser, JWTConfig, AuthenticationError

logger = logging.getLogger("VitalAgentContainerLogger")

# HTTP Bearer token scheme for FastAPI
security = HTTPBearer(auto_error=False)

def get_jwt_config() -> dict:
    """Get JWT configuration from environment variables"""
    return {
        'enabled': os.getenv('JWT_ENABLED', 'false').lower() == 'true',
        'algorithm': os.getenv('JWT_ALGORITHM', 'RS256'),
        'secret_key': os.getenv('JWT_SECRET_KEY'),
        'public_key_path': os.getenv('JWT_PUBLIC_KEY_PATH'),
        'jwks_url': os.getenv('JWT_JWKS_URL'),
        'required_claims': os.getenv('JWT_REQUIRED_CLAIMS', 'sub,exp,iat').split(','),
        'token_expiry_seconds': int(os.getenv('JWT_TOKEN_EXPIRY_SECONDS', '3600')),
        'issuer': os.getenv('JWT_ISSUER'),
        'audience': os.getenv('JWT_AUDIENCE')
    }

def create_authenticated_user_from_jwt(jwt_payload: dict) -> AuthenticatedUser:
    """Create AuthenticatedUser from JWT payload"""
    
    # Extract user ID
    user_id = JWTUtils.extract_user_id(jwt_payload)
    if not user_id:
        raise JWTInvalidClaimsError("User ID not found in JWT payload")
    
    # Extract permissions and roles
    permissions = JWTUtils.extract_user_permissions(jwt_payload)
    roles = jwt_payload.get('roles', [])
    if not isinstance(roles, list):
        roles = []
    
    # Extract standard claims
    subject = jwt_payload.get('sub')
    issuer = jwt_payload.get('iss')
    audience = jwt_payload.get('aud')
    
    # Convert timestamps to datetime objects
    expires_at = None
    if 'exp' in jwt_payload:
        expires_at = datetime.fromtimestamp(jwt_payload['exp'], tz=timezone.utc)
    
    issued_at = None
    if 'iat' in jwt_payload:
        issued_at = datetime.fromtimestamp(jwt_payload['iat'], tz=timezone.utc)
    
    # Extract email
    email = jwt_payload.get('email')
    
    return AuthenticatedUser(
        user_id=user_id,
        email=email,
        permissions=permissions,
        roles=roles,
        jwt_payload=jwt_payload,
        subject=subject,
        issuer=issuer,
        audience=audience,
        expires_at=expires_at,
        issued_at=issued_at
    )

async def get_current_user_dependency(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> AuthenticatedUser:
    """
    FastAPI dependency to get current authenticated user from JWT token
    
    Args:
        request: FastAPI request object
        credentials: HTTP Bearer credentials
        
    Returns:
        AuthenticatedUser object
        
    Raises:
        HTTPException: If authentication fails
    """
    jwt_config = get_jwt_config()
    
    # Check if JWT is enabled
    if not jwt_config.get('enabled', False):
        # JWT disabled - create a default user for development
        logger.warning("JWT authentication is disabled - using default user")
        return AuthenticatedUser(
            user_id="dev_user",
            email="dev@example.com",
            permissions=["*"],  # All permissions for development
            roles=["admin"],
            jwt_payload={"sub": "dev_user", "dev_mode": True}
        )
    
    # Get token from Authorization header
    token = None
    if credentials:
        token = credentials.credentials
    
    if not token:
        logger.warning("No JWT token provided in request")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "authentication_required",
                "message": "JWT token is required",
                "details": {
                    "error_type": "MissingToken",
                    "timestamp": datetime.utcnow().isoformat()
                }
            },
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    try:
        # Validate JWT token
        jwt_payload = JWTUtils.validate_jwt_token(token, jwt_config)
        
        # Create authenticated user
        user = create_authenticated_user_from_jwt(jwt_payload)
        
        # Log successful authentication
        logger.info(f"User authenticated successfully: {user.user_id}")
        
        return user
        
    except JWTExpiredError as e:
        logger.warning(f"JWT token expired for request: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "token_expired",
                "message": str(e),
                "details": {
                    "error_type": "JWTExpiredError",
                    "timestamp": datetime.utcnow().isoformat()
                }
            },
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    except JWTInvalidClaimsError as e:
        logger.warning(f"JWT token has invalid claims: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": "invalid_claims",
                "message": str(e),
                "details": {
                    "error_type": "JWTInvalidClaimsError",
                    "timestamp": datetime.utcnow().isoformat()
                }
            }
        )
    
    except JWTValidationError as e:
        logger.warning(f"JWT token validation failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "authentication_failed",
                "message": str(e),
                "details": {
                    "error_type": "JWTValidationError",
                    "timestamp": datetime.utcnow().isoformat()
                }
            },
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    except Exception as e:
        logger.error(f"Unexpected error during JWT authentication: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "authentication_error",
                "message": "Internal authentication error",
                "details": {
                    "error_type": "InternalError",
                    "timestamp": datetime.utcnow().isoformat()
                }
            }
        )



