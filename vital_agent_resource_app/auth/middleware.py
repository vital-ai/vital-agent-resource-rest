import logging
import time
from typing import Callable, Optional
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from vital_agent_resource_app.auth.jwt_utils import JWTUtils, JWTValidationError, JWTExpiredError, JWTInvalidClaimsError
from vital_agent_resource_app.auth.dependencies import get_jwt_config, create_authenticated_user_from_jwt
from vital_agent_resource_app.data_models.auth_models import AuthenticatedUser
from datetime import datetime

logger = logging.getLogger("VitalAgentContainerLogger")

class JWTAuthenticationMiddleware(BaseHTTPMiddleware):
    """
    Middleware for JWT authentication and request logging
    """
    
    def __init__(self, app: ASGIApp):
        super().__init__(app)
        # Import here to avoid circular imports
        from vital_agent_resource_app.auth.dependencies import get_jwt_config
        self.jwt_config = get_jwt_config()
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process request with JWT authentication and logging
        """
        start_time = time.time()
        
        # Skip authentication for certain paths
        skip_auth_paths = ["/health", "/docs", "/redoc", "/openapi.json"]
        if request.url.path in skip_auth_paths:
            response = await call_next(request)
            return response
        
        # Extract user information if JWT is present (but don't enforce)
        user_info = await self._extract_user_info(request)
        
        # Add user context to request state
        request.state.user = user_info
        request.state.start_time = start_time
        
        try:
            response = await call_next(request)
            
            # Log successful request
            await self._log_request(request, response, user_info, start_time)
            
            return response
            
        except Exception as e:
            # Log failed request
            await self._log_error(request, e, user_info, start_time)
            raise
    
    async def _extract_user_info(self, request: Request) -> Optional[AuthenticatedUser]:
        """
        Extract user information from JWT token if present
        Does not raise exceptions - returns None if token is invalid
        """
        try:
            # Check if JWT is enabled
            if not self.jwt_config.get('enabled', False):
                return None
            
            # Get token from Authorization header
            auth_header = request.headers.get('authorization')
            if not auth_header or not auth_header.startswith('Bearer '):
                return None
            
            token = auth_header[7:]  # Remove 'Bearer ' prefix
            
            # Validate token
            jwt_payload = JWTUtils.validate_jwt_token(token, self.jwt_config)
            
            # Create user object
            user = create_authenticated_user_from_jwt(jwt_payload)
            
            return user
            
        except (JWTValidationError, JWTExpiredError, JWTInvalidClaimsError):
            # Invalid token - return None (don't raise exception in middleware)
            return None
        except Exception as e:
            logger.warning(f"Unexpected error extracting user info: {str(e)}")
            return None
    
    async def _log_request(self, request: Request, response: Response, user: Optional[AuthenticatedUser], start_time: float):
        """
        Log successful request with user context
        """
        duration_ms = int((time.time() - start_time) * 1000)
        
        user_id = user.user_id if user else "anonymous"
        permissions = user.permissions if user else []
        
        logger.info(
            f"Request completed - "
            f"method={request.method} "
            f"path={request.url.path} "
            f"status={response.status_code} "
            f"duration={duration_ms}ms "
            f"user={user_id} "
            f"permissions={len(permissions)}"
        )
    
    async def _log_error(self, request: Request, error: Exception, user: Optional[AuthenticatedUser], start_time: float):
        """
        Log failed request with user context
        """
        duration_ms = int((time.time() - start_time) * 1000)
        
        user_id = user.user_id if user else "anonymous"
        
        logger.error(
            f"Request failed - "
            f"method={request.method} "
            f"path={request.url.path} "
            f"duration={duration_ms}ms "
            f"user={user_id} "
            f"error={str(error)}"
        )

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Simple request logging middleware without authentication
    """
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start_time = time.time()
        
        # Log incoming request
        logger.info(f"Incoming request: {request.method} {request.url.path}")
        
        try:
            response = await call_next(request)
            duration_ms = int((time.time() - start_time) * 1000)
            
            logger.info(
                f"Request completed: {request.method} {request.url.path} "
                f"- Status: {response.status_code}, Duration: {duration_ms}ms"
            )
            
            return response
            
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            
            logger.error(
                f"Request failed: {request.method} {request.url.path} "
                f"- Duration: {duration_ms}ms, Error: {str(e)}"
            )
            
            raise
