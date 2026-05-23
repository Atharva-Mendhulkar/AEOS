"""
AEOS JWT authentication and RBAC middleware.

Provides shared authentication utilities for all AEOS FastAPI services:
- verify_jwt: validate and decode a JWT token
- require_auth: FastAPI dependency that extracts and validates the Bearer token
- require_role: FastAPI dependency factory for RBAC role enforcement
- RBAC_PERMISSIONS: role → permitted action set matrix
"""

from aeos_shared.auth.jwt_auth import (
    JWTPayload,
    RBAC_PERMISSIONS,
    verify_jwt,
    require_auth,
    require_role,
)

__all__ = [
    "JWTPayload",
    "RBAC_PERMISSIONS",
    "verify_jwt",
    "require_auth",
    "require_role",
]
