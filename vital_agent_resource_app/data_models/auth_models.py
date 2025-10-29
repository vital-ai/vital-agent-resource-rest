from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime

class AuthenticatedUser(BaseModel):
    """Model representing an authenticated user from JWT token"""
    
    user_id: str = Field(..., description="Unique user identifier")
    email: Optional[str] = Field(None, description="User email address")
    permissions: List[str] = Field(default_factory=list, description="List of user permissions")
    roles: List[str] = Field(default_factory=list, description="List of user roles")
    jwt_payload: Dict[str, Any] = Field(default_factory=dict, description="Full JWT payload")
    
    # Standard JWT claims
    subject: Optional[str] = Field(None, description="JWT subject claim")
    issuer: Optional[str] = Field(None, description="JWT issuer claim")
    audience: Optional[str] = Field(None, description="JWT audience claim")
    expires_at: Optional[datetime] = Field(None, description="JWT expiration time")
    issued_at: Optional[datetime] = Field(None, description="JWT issued at time")
    
    def has_permission(self, permission: str) -> bool:
        """Check if user has a specific permission"""
        return permission in self.permissions
    
    def has_role(self, role: str) -> bool:
        """Check if user has a specific role"""
        return role in self.roles
    
    def has_any_permission(self, permissions: List[str]) -> bool:
        """Check if user has any of the specified permissions"""
        return any(perm in self.permissions for perm in permissions)
    
    def has_all_permissions(self, permissions: List[str]) -> bool:
        """Check if user has all of the specified permissions"""
        return all(perm in self.permissions for perm in permissions)

class JWTConfig(BaseModel):
    """Model for JWT configuration validation"""
    
    enabled: bool = Field(default=False, description="Enable JWT authentication")
    algorithm: str = Field(default="RS256", description="JWT signing algorithm")
    public_key_path: Optional[str] = Field(None, description="Path to RSA public key file")
    secret_key: Optional[str] = Field(None, description="HMAC secret key")
    jwks_url: Optional[str] = Field(None, description="JWKS URL for fetching public keys")
    enforcement_mode: str = Field(default="header", description="Token enforcement mode")
    required_claims: List[str] = Field(default=["sub", "exp", "iat"], description="Required JWT claims")
    token_expiry_seconds: int = Field(default=3600, description="Token expiry time in seconds")
    issuer: Optional[str] = Field(None, description="Expected JWT issuer")
    audience: Optional[str] = Field(None, description="Expected JWT audience")
    
    class Config:
        extra = "forbid"

class AuthenticationError(BaseModel):
    """Model for authentication error responses"""
    
    error: str = Field(..., description="Error type identifier")
    message: str = Field(..., description="Human-readable error message")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional error details")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Error timestamp")

class TokenValidationResult(BaseModel):
    """Model for token validation results"""
    
    valid: bool = Field(..., description="Whether token is valid")
    user: Optional[AuthenticatedUser] = Field(None, description="Authenticated user if valid")
    error: Optional[AuthenticationError] = Field(None, description="Error details if invalid")
    
class PermissionRequirement(BaseModel):
    """Model for defining permission requirements"""
    
    required_permissions: List[str] = Field(default_factory=list, description="Required permissions")
    required_roles: List[str] = Field(default_factory=list, description="Required roles") 
    require_all_permissions: bool = Field(default=True, description="Require all permissions or any")
    require_all_roles: bool = Field(default=False, description="Require all roles or any")
