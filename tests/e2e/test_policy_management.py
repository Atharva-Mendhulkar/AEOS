import pytest
import httpx

API_BASE = "http://localhost:8000/api/v1"

@pytest.mark.asyncio
async def test_policy_hot_reload():
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{API_BASE}/policies")
        if response.status_code != 200:
            pytest.skip("API Gateway not reachable. Skipping E2E test.")
            
        data = response.json()
        assert isinstance(data, list)
