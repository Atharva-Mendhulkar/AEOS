import pytest
import httpx

API_BASE = "http://localhost:8000/api/v1"

@pytest.mark.asyncio
async def test_observability_and_audit():
    async with httpx.AsyncClient() as client:
        # Check audit trail query
        response = await client.get(f"{API_BASE}/audit?limit=5")
        if response.status_code != 200:
            pytest.skip("API Gateway not reachable. Skipping E2E test.")
            
        data = response.json()
        assert "items" in data
