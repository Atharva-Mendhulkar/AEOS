import pytest
import httpx
from .test_utils import get_auth_headers

API_BASE = "http://localhost:8000/api/v1"

@pytest.mark.asyncio
async def test_memory_state_recovery():
    headers = get_auth_headers()
    async with httpx.AsyncClient(headers=headers) as client:
        # Check incident listing as a proxy for memory retrieval
        response = await client.get(f"{API_BASE}/incidents")
        assert response.status_code == 200, f"Failed with status {response.status_code} and text {response.text}"
            
        data = response.json()
        assert isinstance(data, list)
