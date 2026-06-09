import time
import uuid

import httpx
import pytest

from .test_utils import API_BASE, E2E_TIMEOUT, get_auth_headers, require_aeos_gateway, wait_for_condition


@pytest.mark.asyncio
async def test_full_text_incident_lifecycle_slas():
    await require_aeos_gateway()
    headers = get_auth_headers("admin")
    unique_content = f"critical database error requiring restart {uuid.uuid4()}"

    async with httpx.AsyncClient(headers=headers, timeout=10.0) as client:
        started = time.monotonic()
        response = await client.post(
            f"{API_BASE}/incidents/ingest",
            data={"format": "text", "metadata": '{"source":"phase7-e2e"}'},
            files={"file": ("incident.txt", unique_content.encode("utf-8"), "text/plain")},
        )
        routed_in = time.monotonic() - started

        assert response.status_code == 200, response.text
        assert routed_in <= 5.0, f"routing SLA exceeded: {routed_in:.2f}s"
        input_id = response.json()["incident_id"]

        async def classified_probe():
            res = await client.get(f"{API_BASE}/incidents/{input_id}")
            if res.status_code != 200:
                return None
            incident = res.json()
            return incident if incident.get("severity") and incident.get("workflow_id") else None

        incident = await wait_for_condition("incident classification", classified_probe, timeout=E2E_TIMEOUT)
        assert incident["severity"] in {"critical", "high", "medium", "low"}
        assert incident["root_signature"]

        plan_started = time.monotonic()

        async def workflow_probe():
            res = await client.get(f"{API_BASE}/workflows/{incident['workflow_id']}")
            if res.status_code != 200:
                return None
            workflow = res.json()
            plan = workflow.get("plan") or {}
            return workflow if plan.get("steps") else None

        workflow = await wait_for_condition("planner-generated workflow", workflow_probe, timeout=E2E_TIMEOUT)
        assert time.monotonic() - plan_started <= 10.0
        assert workflow["status"] in {"executing", "suspended", "completed", "failed"}
        for step in workflow["plan"]["steps"]:
            assert step.get("agent_type")
            assert step.get("action", {}).get("tool")
            assert isinstance(step.get("depends_on", []), list)


@pytest.mark.asyncio
async def test_low_confidence_incident_enters_escalation_before_execution():
    await require_aeos_gateway()
    headers = get_auth_headers("admin")
    unique_content = f"ambiguous low confidence operational report {uuid.uuid4()}"

    async with httpx.AsyncClient(headers=headers, timeout=10.0) as client:
        response = await client.post(
            f"{API_BASE}/incidents/ingest",
            data={"format": "text", "metadata": '{"source":"phase7-low-confidence"}'},
            files={"file": ("ambiguous.txt", unique_content.encode("utf-8"), "text/plain")},
        )
        assert response.status_code == 200, response.text
        input_id = response.json()["incident_id"]

        async def escalated_probe():
            res = await client.get(f"{API_BASE}/incidents/{input_id}")
            if res.status_code != 200:
                return None
            incident = res.json()
            return incident if incident.get("status") == "escalated" else None

        incident = await wait_for_condition("low-confidence escalation", escalated_probe, timeout=E2E_TIMEOUT)
        assert incident["severity"] is None
        assert incident["confidence_score"] < 0.7


@pytest.mark.asyncio
async def test_unsupported_format_returns_error_and_audit_entry():
    await require_aeos_gateway()
    headers = get_auth_headers("admin")
    rejected_format = f"unsupported-{uuid.uuid4()}"

    async with httpx.AsyncClient(headers=headers, timeout=10.0) as client:
        response = await client.post(
            f"{API_BASE}/incidents/ingest",
            data={"format": rejected_format, "metadata": '{"source":"phase7-negative"}'},
            files={"file": ("payload.bin", b"bad format", "application/octet-stream")},
        )

        assert response.status_code == 422
        assert "Unsupported format" in response.text

        async def audit_probe():
            res = await client.get(f"{API_BASE}/audit", params={"event_type": "format.rejected", "limit": 20})
            if res.status_code != 200:
                return None
            rows = res.json()
            return rows if any(rejected_format in str(row.get("inputs", {})) for row in rows) else None

        rows = await wait_for_condition("unsupported format audit entry", audit_probe, timeout=15)
        assert any(row["event_type"] == "format.rejected" for row in rows)
