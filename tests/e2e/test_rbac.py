import pytest
import httpx
from .test_utils import get_auth_headers

API_BASE = "http://localhost:8000/api/v1"

@pytest.mark.asyncio
async def test_rbac_and_access_control():
    # 1. Unauthenticated request should be rejected
    async with httpx.AsyncClient() as client:
        payload = {
            "name": "Test Policy",
            "policy_type": "access",
            "config": "{}"
        }
        response = await client.post(f"{API_BASE}/policies", data=payload)
        
        assert response.status_code in [401, 403], f"API Gateway not enforcing auth. Status: {response.status_code}"
            
        assert response.status_code in [401, 403], "RBAC should deny unauthenticated requests"

    # 2. Authenticated request as 'visitor' or 'read_only' should be rejected for POST /policies
    headers = get_auth_headers(role="read_only")
    async with httpx.AsyncClient(headers=headers) as client:
        response2 = await client.post(f"{API_BASE}/policies", data=payload)
        assert response2.status_code in [401, 403], "Read-only role cannot create policies"

