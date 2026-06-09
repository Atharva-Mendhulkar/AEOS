import httpx
import pytest

from .test_utils import API_BASE, get_auth_headers, require_aeos_gateway


@pytest.mark.asyncio
async def test_observability_audit_filters_and_chain_validation():
    await require_aeos_gateway()
    headers = get_auth_headers("admin")
    async with httpx.AsyncClient(headers=headers, timeout=10.0) as client:
        response = await client.get(f"{API_BASE}/audit", params={"limit": 5})
        assert response.status_code == 200, response.text
        rows = response.json()
        assert isinstance(rows, list)
        for row in rows:
            assert {"event_type", "timestamp", "agent_identity", "action_description", "prev_entry_hash"} <= set(row)

        filtered = await client.get(f"{API_BASE}/audit", params={"event_type": "governance.validation", "limit": 5})
        assert filtered.status_code == 200, filtered.text
        assert all(row["event_type"] == "governance.validation" for row in filtered.json())

        chain_response = await client.get(f"{API_BASE}/observability/audit/validate-chain")
        assert chain_response.status_code == 200, chain_response.text
        chain = chain_response.json()
        assert chain["status"] in {"valid", "tampered", "empty"}
        if chain["status"] == "valid":
            assert chain["validated_count"] >= 0


@pytest.mark.asyncio
async def test_observability_agents_status_contract():
    await require_aeos_gateway()
    headers = get_auth_headers("admin")
    async with httpx.AsyncClient(headers=headers, timeout=10.0) as client:
        response = await client.get(f"{API_BASE}/observability/agents")
        assert response.status_code == 200, response.text

        data = response.json()
        assert isinstance(data, dict)
        for state in data.values():
            assert {"status", "active_steps", "last_active"} <= set(state)
