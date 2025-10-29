import os
import logging
from typing import Dict, Any, Optional, List
import jwt
from jwt.exceptions import InvalidTokenError, ExpiredSignatureError, InvalidSignatureError
import requests
import json
from cryptography.hazmat.primitives import serialization

logger = logging.getLogger("VitalAgentContainerLogger")

class JWTValidationError(Exception):
    """Base exception for JWT validation errors"""
    pass

class JWTExpiredError(JWTValidationError):
    """JWT token has expired"""
    pass

class JWTInvalidClaimsError(JWTValidationError):
    """JWT token has invalid or missing required claims"""
    pass

class JWTUtils:
    """Utility class for JWT token validation and user extraction"""
    
    @staticmethod
    def _fetch_jwks_keys(jwks_url: str) -> dict:
        """Fetch JWKS keys from URL"""
        try:
            response = requests.get(jwks_url, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Failed to fetch JWKS from {jwks_url}: {e}")
            raise JWTValidationError(f"Failed to fetch JWKS: {e}")
    
    @staticmethod
    def _get_public_key_from_jwks(jwks_data: dict, kid: str) -> str:
        """Extract public key from JWKS data using key ID"""
        keys = jwks_data.get('keys', [])
        for key in keys:
            if key.get('kid') == kid:
                if key.get('kty') == 'RSA':
                    # Convert JWK to PEM format
                    from jwt.algorithms import RSAAlgorithm
                    return RSAAlgorithm.from_jwk(json.dumps(key))
        raise JWTValidationError(f"Key with kid '{kid}' not found in JWKS")
    
    @staticmethod
    def _get_signing_key(jwt_config: dict, token: str = None) -> str:
        """Get the appropriate signing key based on configuration"""
        algorithm = jwt_config.get('algorithm', 'RS256')
        
        # For HMAC algorithms, use secret key
        if algorithm.startswith('HS'):
            secret_key = jwt_config.get('secret_key')
            if not secret_key:
                raise JWTValidationError("secret_key is required for HMAC algorithms")
            return secret_key
        
        # For RSA algorithms, try JWKS URL first, then public key path
        jwks_url = jwt_config.get('jwks_url')
        if jwks_url:
            if token:
                # Decode token header to get kid
                try:
                    header = jwt.get_unverified_header(token)
                    kid = header.get('kid')
                    if not kid:
                        raise JWTValidationError("Token header missing 'kid' field required for JWKS")
                    
                    jwks_data = JWTUtils._fetch_jwks_keys(jwks_url)
                    return JWTUtils._get_public_key_from_jwks(jwks_data, kid)
                except Exception as e:
                    logger.error(f"Failed to get key from JWKS: {e}")
                    raise JWTValidationError(f"JWKS key retrieval failed: {e}")
            else:
                raise JWTValidationError("Token required to extract kid for JWKS lookup")
        
        # Fall back to public key file
        public_key_path = jwt_config.get('public_key_path')
        if not public_key_path:
            raise JWTValidationError("Either jwks_url or public_key_path is required for RSA algorithms")
        
        if not os.path.exists(public_key_path):
            raise JWTValidationError(f"Public key file not found: {public_key_path}")
        
        with open(public_key_path, 'r') as f:
            return f.read()
    
    @staticmethod
    def validate_jwt_token(token: str, jwt_config: dict) -> Dict[str, Any]:
        """
        Validate and decode a JWT token
        
        Args:
            token: JWT token string
            jwt_config: JWT configuration dictionary
            
        Returns:
            Dict containing decoded JWT payload
            
        Raises:
            JWTValidationError: If token validation fails
            JWTExpiredError: If token has expired
            JWTInvalidClaimsError: If required claims are missing
        """
        try:
            # Remove 'Bearer ' prefix if present
            if token.startswith('Bearer '):
                token = token[7:]
            
            # Get signing key based on algorithm and configuration
            algorithm = jwt_config.get('algorithm', 'RS256')
            signing_key = JWTUtils._get_signing_key(jwt_config, token)
            
            # Decode and validate the token with issuer and audience validation
            decode_options = {"verify_exp": True, "verify_iat": True}
            decode_kwargs = {
                "jwt": token,
                "key": signing_key,
                "algorithms": [algorithm],
                "options": decode_options
            }
            
            # Add issuer validation if configured
            issuer = jwt_config.get('issuer')
            if issuer:
                decode_kwargs["issuer"] = issuer
            
            # Add audience validation if configured
            audience = jwt_config.get('audience')
            if audience:
                decode_kwargs["audience"] = audience
            
            payload = jwt.decode(**decode_kwargs)
            
            # Validate required claims
            required_claims = jwt_config.get('required_claims', ['sub', 'exp', 'iat'])
            missing_claims = [claim for claim in required_claims if claim not in payload]
            if missing_claims:
                raise JWTInvalidClaimsError(f"Missing required claims: {missing_claims}")
            
            # Log successful validation (without sensitive data)
            logger.info(f"JWT token validated successfully for subject: {payload.get('sub', 'unknown')}")
            
            return payload
            
        except jwt.ExpiredSignatureError:
            logger.warning("JWT token has expired")
            raise JWTExpiredError("JWT token has expired")
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid JWT token: {str(e)}")
            raise JWTValidationError(f"Invalid JWT token: {str(e)}")
        except Exception as e:
            logger.error(f"JWT validation error: {str(e)}")
            raise JWTValidationError(f"JWT validation failed: {str(e)}")
    
    @staticmethod
    def extract_user_permissions(jwt_payload: Dict[str, Any]) -> List[str]:
        """
        Extract user permissions from JWT payload
        
        Args:
            jwt_payload: Decoded JWT payload
            
        Returns:
            List of permission strings
        """
        # Try common permission claim names
        permissions = jwt_payload.get('permissions', [])
        if not permissions:
            permissions = jwt_payload.get('perms', [])
        if not permissions:
            permissions = jwt_payload.get('roles', [])
        
        return permissions if isinstance(permissions, list) else []
    
    @staticmethod
    def extract_user_id(jwt_payload: Dict[str, Any]) -> Optional[str]:
        """
        Extract user ID from JWT payload
        
        Args:
            jwt_payload: Decoded JWT payload
            
        Returns:
            User ID string or None
        """
        # Try common user ID claim names
        user_id = jwt_payload.get('sub')  # Standard 'subject' claim
        if not user_id:
            user_id = jwt_payload.get('user_id')
        if not user_id:
            user_id = jwt_payload.get('uid')
        
        return user_id
    
    @staticmethod
    def has_permission(jwt_payload: Dict[str, Any], required_permission: str) -> bool:
        """
        Check if JWT payload contains a specific permission
        
        Args:
            jwt_payload: Decoded JWT payload
            required_permission: Permission string to check for
            
        Returns:
            True if permission is present, False otherwise
        """
        permissions = JWTUtils.extract_user_permissions(jwt_payload)
        return required_permission in permissions
    
    @staticmethod
    def validate_jwt_config(jwt_config: Dict[str, Any]) -> bool:
        """
        Validate JWT configuration
        
        Args:
            jwt_config: JWT configuration dictionary
            
        Returns:
            True if configuration is valid
            
        Raises:
            ValueError: If configuration is invalid
        """
        if not jwt_config.get('enabled', False):
            return True  # Skip validation if JWT is disabled
        
        algorithm = jwt_config.get('algorithm', 'RS256')
        
        if algorithm.startswith('RS'):
            # RSA algorithms require public key file
            public_key_path = jwt_config.get('public_key_path')
            if not public_key_path:
                raise ValueError("public_key_path is required for RSA algorithms")
            if not os.path.exists(public_key_path):
                raise ValueError(f"Public key file not found: {public_key_path}")
        else:
            # HMAC algorithms require secret key
            secret_key = jwt_config.get('secret_key')
            if not secret_key:
                raise ValueError("secret_key is required for HMAC algorithms")
        
        enforcement_mode = jwt_config.get('enforcement_mode', 'header')
        if enforcement_mode not in ['header', 'payload', 'hybrid', 'none']:
            raise ValueError(f"Invalid enforcement_mode: {enforcement_mode}")
        
        logger.info(f"JWT configuration validated: algorithm={algorithm}, mode={enforcement_mode}")
        return True
