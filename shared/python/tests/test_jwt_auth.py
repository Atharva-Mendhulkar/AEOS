"""
Unit tests for JWT authentication and RBAC enforcement.

Tests verify:
- Token validation (valid tokens, invalid signatures, malformed tokens)
- Token expiry (expired tokens are rejected)
- Role enforcement (require_role correctly validates roles)
- RBAC permission matrix
"""

from __future__ import annotations

import os
import time
from unittest.mock import patch

import pytest
from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient
from jose import jwt

# Set up test secret before importing auth module
os.environ["AEOS_JWT_SECRET"] = "test-secret-key-for-testing"

from aeos_shared.auth.jwt_auth import (
    JWTPayload,
    RBAC_PERMISSIONS,
    verify_jwt,
    require_auth,
    require_role,
    ALGORITHM,
    TOKEN_EXPIRY_SECONDS,
)


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------

TEST_SECRET = "test-secret-key-for-testing"


def create_valid_token(
    subject: str = "test-user",
    role: str = "admin",
    expired: bool = False,
) -> str:
    """Create a valid JWT token for testing."""
    now = int(time.time())
    if expired:
        # Token expired 1 hour ago
        exp = now - TOKEN_EXPIRY_SECONDS - 1
    else:
        # Token expires 1 hour from now
        exp = now + TOKEN_EXPIRY_SECONDS

    payload = {
        "sub": subject,
        "role": role,
        "exp": exp,
        "iat": now,
    }
    return jwt.encode(payload, TEST_SECRET, algorithm=ALGORITHM)


def create_token_with_invalid_signature() -> str:
    """Create a token with an invalid signature."""
    now = int(time.time())
    payload = {
        "sub": "test-user",
        "role": "admin",
        "exp": now + TOKEN_EXPIRY_SECONDS,
        "iat": now,
    }
    # Sign with a different secret
    return jwt.encode(payload, "wrong-secret", algorithm=ALGORITHM)


def create_malformed_token() -> str:
    """Create a malformed JWT token."""
    return "not-a-valid-jwt-token"


def create_token_with_missing_claims() -> str:
    """Create a token missing required claims."""
    now = int(time.time())
    payload = {
        "sub": "test-user",
        # Missing "role" claim
        "exp": now + TOKEN_EXPIRY_SECONDS,
        "iat": now,
    }
    return jwt.encode(payload, TEST_SECRET, algorithm=ALGORITHM)


# ---------------------------------------------------------------------------
# Tests: verify_jwt
# ---------------------------------------------------------------------------


class TestVerifyJwt:
    """Tests for the verify_jwt function."""

    def test_valid_token_returns_payload(self):
        """A valid token should be decoded and returned as JWTPayload."""
        token = create_valid_token(subject="user-123", role="operator")
        result = verify_jwt(token)

        assert isinstance(result, JWTPayload)
        assert result.sub == "user-123"
        assert result.role == "operator"

    def test_invalid_signature_raises_401(self):
        """A token with invalid signature should raise 401."""
        token = create_token_with_invalid_signature()

        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            verify_jwt(token)
        assert exc_info.value.status_code == 401
        assert "Could not validate credentials" in exc_info.value.detail

    def test_malformed_token_raises_401(self):
        """A malformed token should raise 401."""
        token = create_malformed_token()

        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            verify_jwt(token)
        assert exc_info.value.status_code == 401

    def test_expired_token_raises_401(self):
        """An expired token should raise 401 with specific message."""
        token = create_valid_token(expired=True)

        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            verify_jwt(token)
        assert exc_info.value.status_code == 401
        assert "expired" in exc_info.value.detail.lower()

    def test_token_with_missing_claims_raises_401(self):
        """A token missing required claims should raise 401."""
        token = create_token_with_missing_claims()

        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            verify_jwt(token)
        assert exc_info.value.status_code == 401


class TestRequireAuth:
    """Tests for the require_auth FastAPI dependency."""

    def test_require_auth_valid_token(self):
        """require_auth should return JWTPayload for valid Bearer token."""
        app = FastAPI()

        @app.get("/protected")
        async def protected_route(payload: JWTPayload = Depends(require_auth)):
            return {"sub": payload.sub, "role": payload.role}

        client = TestClient(app)
        token = create_valid_token(subject="test-user", role="admin")
        response = client.get(
            "/protected",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        assert response.json() == {"sub": "test-user", "role": "admin"}

    def test_require_auth_missing_header(self):
        """require_auth should return 401 when Authorization header is missing."""
        app = FastAPI()

        @app.get("/protected")
        async def protected_route(payload: JWTPayload = Depends(require_auth)):
            return {"sub": payload.sub}

        client = TestClient(app)
        response = client.get("/protected")

        assert response.status_code == 401
        assert "missing" in response.json()["detail"].lower()

    def test_require_auth_invalid_scheme(self):
        """require_auth should return 401 when scheme is not Bearer."""
        app = FastAPI()

        @app.get("/protected")
        async def protected_route(payload: JWTPayload = Depends(require_auth)):
            return {"sub": payload.sub}

        client = TestClient(app)
        response = client.get(
            "/protected",
            headers={"Authorization": "Basic dXNlcjpwYXNz"}
        )

        assert response.status_code == 401


# ---------------------------------------------------------------------------
# Tests: require_role
# ---------------------------------------------------------------------------


class TestRequireRole:
    """Tests for the require_role FastAPI dependency."""

    def test_require_role_allowed_role(self):
        """require_role should allow access for permitted roles."""
        app = FastAPI()

        @app.get("/admin-only")
        async def admin_route(
            payload: JWTPayload = Depends(require_role(["admin", "compliance"]))
        ):
            return {"role": payload.role}

        client = TestClient(app)
        token = create_valid_token(role="admin")
        response = client.get(
            "/admin-only",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        assert response.json()["role"] == "admin"

    def test_require_role_unauthorized_role(self):
        """require_role should deny access for non-permitted roles."""
        app = FastAPI()

        @app.get("/admin-only")
        async def admin_route(
            payload: JWTPayload = Depends(require_role(["admin", "compliance"]))
        ):
            return {"role": payload.role}

        client = TestClient(app)
        token = create_valid_token(role="read_only")
        response = client.get(
            "/admin-only",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 403
        assert "not authorised" in response.json()["detail"].lower()

    def test_require_role_compliance_role_allowed(self):
        """Compliance role should be allowed on compliance-protected endpoints."""
        app = FastAPI()

        @app.get("/compliance-only")
        async def compliance_route(
            payload: JWTPayload = Depends(require_role(["compliance"]))
        ):
            return {"role": payload.role}

        client = TestClient(app)
        token = create_valid_token(role="compliance")
        response = client.get(
            "/compliance-only",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200

    def test_require_role_multiple_allowed_roles(self):
        """Multiple allowed roles should grant access to any of them."""
        app = FastAPI()

        @app.get("/operators")
        async def operator_route(
            payload: JWTPayload = Depends(require_role(["operator", "admin"]))
        ):
            return {"role": payload.role}

        client = TestClient(app)

        # Test operator role
        token_op = create_valid_token(role="operator")
        response_op = client.get(
            "/operators",
            headers={"Authorization": f"Bearer {token_op}"}
        )
        assert response_op.status_code == 200

        # Test admin role
        token_admin = create_valid_token(role="admin")
        response_admin = client.get(
            "/operators",
            headers={"Authorization": f"Bearer {token_admin}"}
        )
        assert response_admin.status_code == 200


# ---------------------------------------------------------------------------
# Tests: RBAC permissions matrix
# ---------------------------------------------------------------------------


class TestRBACPermissions:
    """Tests for the RBAC permission matrix."""

    def test_all_roles_defined(self):
        """All required roles should be defined in RBAC_PERMISSIONS."""
        required_roles = {"read_only", "operator", "admin", "compliance"}
        assert required_roles == set(RBAC_PERMISSIONS.keys())

    def test_read_only_has_only_read(self):
        """read_only role should only have 'read' permission."""
        assert RBAC_PERMISSIONS["read_only"] == {"read"}

    def test_operator_has_read_and_execute(self):
        """operator role should have 'read' and 'execute' permissions."""
        expected = {"read", "execute"}
        assert RBAC_PERMISSIONS["operator"] == expected

    def test_admin_has_all_permissions(self):
        """admin role should have all permissions."""
        expected = {
            "read",
            "execute",
            "write",
            "delete",
            "manage_policies",
            "manage_users",
        }
        assert RBAC_PERMISSIONS["admin"] == expected

    def test_compliance_has_read_and_manage_policies(self):
        """compliance role should have 'read' and 'manage_policies' permissions."""
        expected = {"read", "manage_policies"}
        assert RBAC_PERMISSIONS["compliance"] == expected


# ---------------------------------------------------------------------------
# Tests: JWTPayload model
# ---------------------------------------------------------------------------


class TestJWTPayload:
    """Tests for the JWTPayload Pydantic model."""

    def test_valid_payload_creation(self):
        """JWTPayload should be created with valid claims."""
        now = int(time.time())
        payload = JWTPayload(
            sub="user-123",
            role="admin",
            exp=now + 3600,
            iat=now,
        )
        assert payload.sub == "user-123"
        assert payload.role == "admin"

    def test_payload_requires_sub(self):
        """JWTPayload should require 'sub' field."""
        now = int(time.time())
        with pytest.raises(Exception):
            JWTPayload(
                role="admin",
                exp=now + 3600,
                iat=now,
            )

    def test_payload_requires_role(self):
        """JWTPayload should require 'role' field."""
        now = int(time.time())
        with pytest.raises(Exception):
            JWTPayload(
                sub="user-123",
                exp=now + 3600,
                iat=now,
            )