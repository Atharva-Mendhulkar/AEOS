import uuid

import httpx
import pytest

from .test_utils import API_BASE, get_auth_headers, require_aeos_gateway, wait_for_condition


def permission_config(agent_type="operations", tools=None):
    return {
        "agent_type": agent_type,
        "allowed_tools": tools or ["gather_logs", "restart_service"],
        "denied_tools": [],
    }


@pytest.mark.asyncio
async def test_policy_crud_hot_reload_and_audit_trail():
    await require_aeos_gateway()
    headers = get_auth_headers("admin")
    name = f"phase7-permission-{uuid.uuid4()}"

    async with httpx.AsyncClient(headers=headers, timeout=10.0) as client:
        create_response = await client.post(
            f"{API_BASE}/policies",
            data={
                "name": name,
                "policy_type": "permission",
                "config": '{"agent_type":"operations","allowed_tools":["gather_logs"],"denied_tools":[]}',
            },
        )
        assert create_response.status_code == 200, create_response.text
        policy_id = create_response.json()["id"]

        async def listed_probe():
            res = await client.get(f"{API_BASE}/policies")
            assert res.status_code == 200, res.text
            return next((policy for policy in res.json() if policy["id"] == policy_id), None)

        created = await wait_for_condition("created policy to appear", listed_probe, timeout=10)
        assert created["name"] == name
        assert created["version"] == 1
        assert created["is_active"] is True

        update_response = await client.put(
            f"{API_BASE}/policies/{policy_id}",
            data={
                "name": f"{name}-updated",
                "config": '{"agent_type":"operations","allowed_tools":["gather_logs","restart_service"],"denied_tools":[]}',
            },
        )
        assert update_response.status_code == 200, update_response.text
        assert update_response.json()["version"] == 2

        invalid_response = await client.post(
            f"{API_BASE}/policies",
            data={"name": f"{name}-invalid", "policy_type": "permission", "config": '{"allowed_tools":[]}'},
        )
        assert invalid_response.status_code == 422

        delete_response = await client.delete(f"{API_BASE}/policies/{policy_id}")
        assert delete_response.status_code == 200, delete_response.text

        async def audit_probe():
            res = await client.get(f"{API_BASE}/audit", params={"agent_identity": "api-gateway", "limit": 50})
            assert res.status_code == 200, res.text
            rows = res.json()
            events = {row["event_type"] for row in rows if policy_id in str(row)}
            return events if {"policy.created", "policy.updated", "policy.deactivated"}.issubset(events) else None

        events = await wait_for_condition("policy change audit entries", audit_probe, timeout=15)
        assert "policy.created" in events
        assert "policy.updated" in events
        assert "policy.deactivated" in events
