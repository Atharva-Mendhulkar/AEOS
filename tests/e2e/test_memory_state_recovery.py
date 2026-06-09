import uuid

import httpx
import pytest

from .test_utils import API_BASE, get_auth_headers, require_aeos_gateway, wait_for_condition


@pytest.mark.asyncio
async def test_memory_state_is_queryable_after_workflow_creation():
    await require_aeos_gateway()
    headers = get_auth_headers("admin")

    async with httpx.AsyncClient(headers=headers, timeout=10.0) as client:
        response = await client.post(
            f"{API_BASE}/incidents/ingest",
            data={"format": "text", "metadata": '{"source":"phase7-memory"}'},
            files={"file": ("memory.txt", f"warning memory recovery probe {uuid.uuid4()}".encode(), "text/plain")},
        )
        assert response.status_code == 200, response.text
        input_id = response.json()["incident_id"]

        async def incident_probe():
            res = await client.get(f"{API_BASE}/incidents/{input_id}")
            if res.status_code != 200:
                return None
            incident = res.json()
            return incident if incident.get("workflow_id") else None

        incident = await wait_for_condition("incident workflow linkage", incident_probe, timeout=60)

        workflow_response = await client.get(f"{API_BASE}/workflows/{incident['workflow_id']}")
        assert workflow_response.status_code == 200, workflow_response.text
        workflow = workflow_response.json()
        assert workflow["incident_id"] == incident["id"]
        assert workflow["status"] in {"planning", "executing", "suspended", "completed", "failed"}

        incident_list = await client.get(f"{API_BASE}/incidents", params={"limit": 50})
        assert incident_list.status_code == 200, incident_list.text
        assert any(row["id"] == incident["id"] for row in incident_list.json())
