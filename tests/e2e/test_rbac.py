import uuid

import httpx
import pytest

from .test_utils import API_BASE, get_auth_headers, require_aeos_gateway


@pytest.mark.asyncio
async def test_rbac_policy_write_access_matrix():
    await require_aeos_gateway()
    valid_payload = {
        "name": f"phase7-rbac-{uuid.uuid4()}",
        "policy_type": "permission",
        "config": '{"agent_type":"operations","allowed_tools":["gather_logs"],"denied_tools":[]}',
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        unauthenticated = await client.post(f"{API_BASE}/policies", data=valid_payload)
        assert unauthenticated.status_code in {401, 403}

    for role in ("read_only", "operator"):
        async with httpx.AsyncClient(headers=get_auth_headers(role), timeout=10.0) as client:
            response = await client.post(
                f"{API_BASE}/policies",
                data={**valid_payload, "name": f"phase7-rbac-{role}-{uuid.uuid4()}"},
            )
            assert response.status_code == 403, f"{role} unexpectedly created a policy: {response.text}"

    for role in ("admin", "compliance"):
        name = f"phase7-rbac-{role}-{uuid.uuid4()}"
        async with httpx.AsyncClient(headers=get_auth_headers(role), timeout=10.0) as client:
            response = await client.post(f"{API_BASE}/policies", data={**valid_payload, "name": name})
            assert response.status_code == 200, response.text
            policy_id = response.json()["id"]
            cleanup = await client.delete(f"{API_BASE}/policies/{policy_id}")
            assert cleanup.status_code == 200, cleanup.text
