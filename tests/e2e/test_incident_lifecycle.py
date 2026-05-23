import pytest
import httpx
import asyncio
from .test_utils import get_auth_headers

API_BASE = "http://localhost:8000/api/v1"

@pytest.mark.asyncio
async def test_full_incident_lifecycle():
    headers = get_auth_headers()
    async with httpx.AsyncClient(headers=headers) as client:
        # 1. Submit incident (simulate text ingestion)
        payload = {"format": "text", "metadata": '{"source": "test"}'}
        files = {"file": ("test.txt", b"System is experiencing high CPU load", "text/plain")}
        
        response = await client.post(f"{API_BASE}/incidents/ingest", data=payload, files=files)
        
        assert response.status_code == 200, f"Failed with status {response.status_code} and text {response.text}"
            
        data = response.json()
        assert "incident_id" in data
        
        incident_id = data["incident_id"]
        
        # 2. Poll for incident classification
        classified = False
        for _ in range(20):
            res = await client.get(f"{API_BASE}/incidents/{incident_id}")
            if res.status_code == 200:
                inc_data = res.json()
                if inc_data.get("status") not in ["pending", "routing"]:
                    classified = True
                    break
            await asyncio.sleep(1)
            
        assert classified, "Incident classification timed out"
