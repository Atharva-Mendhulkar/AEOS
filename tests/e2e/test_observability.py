import pytest
import httpx
from .test_utils import get_auth_headers

API_BASE = "http://localhost:8000/api/v1"

@pytest.mark.asyncio
async def test_observability_and_audit():
    headers = get_auth_headers()
    async with httpx.AsyncClient(headers=headers) as client:
        # Check audit trail query
        response = await client.get(f"{API_BASE}/audit?limit=5")
        assert response.status_code == 200, f"Failed with status {response.status_code} and text {response.text}"
            
        data = response.json()
        assert isinstance(data, list)
