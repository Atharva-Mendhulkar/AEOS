"""
JWT authentication and RBAC enforcement for AEOS FastAPI services.

All AEOS backend services share this module to validate Bearer tokens
and enforce role-based access control (RBAC).

Token format: HS256-signed JWT, 1-hour expiry.
Required claims: sub (str), role (str), exp (int), iat (int).

Environment variable:
    AEOS_JWT_SECRET — the HMAC-SHA256 signing secret (required at runtime).
"""

from __future__ import annotations

import os
from typing import Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import ExpiredSignatureError, JWTError, jwt
from pydantic import BaseModel, ValidationError

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

ALGORITHM = "HS256"
TOKEN_EXPIRY_SECONDS = 3600  # 1 hour

_bearer_scheme = HTTPBearer(auto_error=False)


def _get_secret() -> str:
    """Return the JWT signing secret from the environment.

    Raises RuntimeError if the variable is not set, so misconfigured
    deployments fail loudly at request time rather than silently.
    """
    secret = os.environ.get("AEOS_JWT_SECRET", "")
    if not secret:
        raise RuntimeError(
            "AEOS_JWT_SECRET environment variable is not set. "
            "All AEOS services require this secret to validate JWT tokens."
        )
    return secret


# ---------------------------------------------------------------------------
# RBAC permission matrix
# ---------------------------------------------------------------------------

#: Maps each role to the set of actions it is permitted to perform.
#: Actions are coarse-grained capability strings used by require_role().
RBAC_PERMISSIONS: dict[str, set[str]] = {
    "read_only": {
        "read",
    },
    "operator": {
        "read",
        "execute",
    },
    "admin": {
        "read",
        "execute",
        "write",
        "delete",
        "manage_policies",
        "manage_users",
    },
    "compliance": {
        "read",
        "manage_policies",
    },
}

# ---------------------------------------------------------------------------
# Pydantic payload model
# ---------------------------------------------------------------------------


class JWTPayload(BaseModel):
    """Validated claims extracted from a decoded AEOS JWT.

    Fields
    ------
    sub:  Subject — typically the user ID or service account identifier.
    role: RBAC role assigned to the subject (read_only | operator | admin | compliance).
    exp:  Expiry time as a Unix timestamp (seconds since epoch).
    iat:  Issued-at time as a Unix timestamp (seconds since epoch).
    """

    sub: str
    role: str
    exp: int
    iat: int


# ---------------------------------------------------------------------------
# Core verification function
# ---------------------------------------------------------------------------


def verify_jwt(token: str) -> JWTPayload:
    """Decode and validate a JWT token string.

    Parameters
    ----------
    token:
        The raw JWT string (without the ``Bearer `` prefix).

    Returns
    -------
    JWTPayload
        The validated payload extracted from the token.

    Raises
    ------
    HTTPException(401)
        If the token is missing required claims, has an invalid signature,
        is malformed, or has expired.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    expired_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token has expired",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        secret = _get_secret()
        payload_dict: dict = jwt.decode(
            token,
            secret,
            algorithms=[ALGORITHM],
        )
    except ExpiredSignatureError:
        raise expired_exception
    except JWTError:
        raise credentials_exception

    try:
        payload = JWTPayload(**payload_dict)
    except (ValidationError, TypeError):
        raise credentials_exception

    return payload


# ---------------------------------------------------------------------------
# FastAPI dependencies
# ---------------------------------------------------------------------------


async def require_auth(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> JWTPayload:
    """FastAPI dependency: extract and validate the Bearer token.

    Reads the ``Authorization: Bearer <token>`` header, verifies the JWT,
    and returns the decoded :class:`JWTPayload`.

    Raises
    ------
    HTTPException(401)
        If the Authorization header is absent, the scheme is not ``Bearer``,
        or the token fails validation.
    """
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header missing or invalid scheme",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return verify_jwt(credentials.credentials)


def require_role(roles: list[str]) -> Callable[..., JWTPayload]:
    """FastAPI dependency factory: enforce that the caller holds one of the given roles.

    Parameters
    ----------
    roles:
        List of role strings that are permitted to access the endpoint.
        At least one must match the ``role`` claim in the token.

    Returns
    -------
    Callable
        A FastAPI dependency that returns the :class:`JWTPayload` when the
        role check passes.

    Raises
    ------
    HTTPException(403)
        If the authenticated user's role is not in the ``roles`` list.

    Example
    -------
    ::

        @router.post("/policies")
        async def create_policy(
            payload: JWTPayload = Depends(require_role(["admin", "compliance"])),
        ):
            ...
    """

    async def _dependency(
        payload: JWTPayload = Depends(require_auth),
    ) -> JWTPayload:
        if payload.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Role '{payload.role}' is not authorised for this endpoint. "
                    f"Required: {roles}"
                ),
            )
        return payload

    return _dependency
