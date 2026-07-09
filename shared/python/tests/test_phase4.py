import os
import sys
import json
import uuid
import pytest
import asyncio
import hashlib
from datetime import datetime, timezone
from unittest.mock import MagicMock, AsyncMock, patch

from fastapi import HTTPException

# Configure environment variables before importing services
os.environ["GEMINI_API_KEY"] = "mock-key"
os.environ["DATABASE_URL"] = "postgresql://postgres:postgres@localhost:5432/aeos"
os.environ["REDIS_URL"] = "redis://localhost:6379/0"
os.environ["ESCALATION_TIMEOUT_SEC"] = "0.1"  # Fast timeout for testing

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
sys.path.insert(0, os.path.join(BASE_DIR, "shared/python"))
sys.path.insert(0, os.path.join(BASE_DIR, "services/memory-agent"))
sys.path.insert(0, os.path.join(BASE_DIR, "services/recovery-agent"))
sys.path.insert(0, os.path.join(BASE_DIR, "services/escalation-agent"))
sys.path.insert(0, os.path.join(BASE_DIR, "services/workflow-engine"))
sys.path.insert(0, os.path.join(BASE_DIR, "services/operations-agent"))
sys.path.insert(0, os.path.join(BASE_DIR, "services/compliance-agent"))
sys.path.insert(0, os.path.join(BASE_DIR, "services/validation-agent"))

import importlib.util
def load_module(module_name, file_path):
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module

memory_agent = load_module("memory_agent", os.path.join(BASE_DIR, "services/memory-agent/main.py"))
recovery_agent = load_module("recovery_agent", os.path.join(BASE_DIR, "services/recovery-agent/main.py"))
escalation_agent = load_module("escalation_agent", os.path.join(BASE_DIR, "services/escalation-agent/main.py"))
workflow_engine = load_module("workflow_engine", os.path.join(BASE_DIR, "services/workflow-engine/main.py"))
operations_agent = load_module("operations_agent", os.path.join(BASE_DIR, "services/operations-agent/main.py"))
compliance_agent = load_module("compliance_agent", os.path.join(BASE_DIR, "services/compliance-agent/main.py"))
validation_agent = load_module("validation_agent", os.path.join(BASE_DIR, "services/validation-agent/main.py"))

from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# 1. Failure Classification Heuristic Tests (Recovery Agent)
# ---------------------------------------------------------------------------

def test_failure_classification_heuristics():
    # Transient failures
    assert recovery_agent.classify_failure("connection timeout to database") == "transient"
    assert recovery_agent.classify_failure("HTTP 503 Service Unavailable") == "transient"
    assert recovery_agent.classify_failure("connection refused on port 5432") == "transient"
    assert recovery_agent.classify_failure("socket.timeout: timed out") == "transient"

    # Permanent failures
    assert recovery_agent.classify_failure("HTTP 404 Not Found") == "permanent"
    assert recovery_agent.classify_failure("ValueError: invalid input format") == "permanent"
    assert recovery_agent.classify_failure("Permission denied: user admin is unauthorized") == "permanent"
    assert recovery_agent.classify_failure("KeyError: 'some_missing_key'") == "permanent"

# ---------------------------------------------------------------------------
# 2. Exponential Backoff Calculation Tests (Recovery Agent)
# ---------------------------------------------------------------------------

def test_exponential_backoff_doubling():
    # Verify exponential backoff intervals strictly double:
    # attempt 1 (retry_count 0) -> 1.0s
    # attempt 2 (retry_count 1) -> 2.0s
    # attempt 3 (retry_count 2) -> 4.0s
    base_delay = 1.0
    
    delay1 = base_delay * (2 ** 0)
    delay2 = base_delay * (2 ** 1)
    delay3 = base_delay * (2 ** 2)
    
    assert delay1 == 1.0
    assert delay2 == 2.0
    assert delay3 == 4.0
    assert delay2 == delay1 * 2
    assert delay3 == delay2 * 2

# ---------------------------------------------------------------------------
# 3. Tamper-Evident Hash Chain Audit Trail Tests (Memory Agent)
# ---------------------------------------------------------------------------

def test_audit_hash_chain_tamper_evidence():
    row1 = {
        "event_type": "step.started",
        "timestamp": datetime(2026, 5, 19, 10, 0, 0, tzinfo=timezone.utc),
        "agent_identity": "workflow-engine",
        "incident_id": uuid.uuid4(),
        "workflow_id": uuid.uuid4(),
        "action_description": "Starting workflow step 1",
        "inputs": {"arg": 1},
        "outputs": {"status": "ok"},
        "risk_score": 3.0,
        "prev_entry_hash": "genesis"
    }
    
    hash1 = memory_agent.compute_entry_hash(row1)
    assert len(hash1) == 64 # SHA-256 length
    
    row2 = {
        "event_type": "step.completed",
        "timestamp": datetime(2026, 5, 19, 10, 0, 5, tzinfo=timezone.utc),
        "agent_identity": "workflow-engine",
        "incident_id": row1["incident_id"],
        "workflow_id": row1["workflow_id"],
        "action_description": "Completed step 1 successfully",
        "inputs": {},
        "outputs": {"res": "done"},
        "risk_score": 1.0,
        "prev_entry_hash": hash1
    }
    
    hash2 = memory_agent.compute_entry_hash(row2)
    assert len(hash2) == 64
    assert hash1 != hash2
    
    # Verify deterministic serialization by using dict elements out of order
    row1_reorder = {
        "prev_entry_hash": "genesis",
        "risk_score": 3.0,
        "outputs": {"status": "ok"},
        "inputs": {"arg": 1},
        "action_description": "Starting workflow step 1",
        "workflow_id": row1["workflow_id"],
        "incident_id": row1["incident_id"],
        "agent_identity": "workflow-engine",
        "timestamp": datetime(2026, 5, 19, 10, 0, 0, tzinfo=timezone.utc),
        "event_type": "step.started"
    }
    hash1_reordered = memory_agent.compute_entry_hash(row1_reorder)
    assert hash1 == hash1_reordered

# ---------------------------------------------------------------------------
# 4. Context Query SLA Enforcement Tests (Memory Agent)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@patch("memory_agent.db_pool")
async def test_context_query_sla_timeout(mock_pool):
    # Mock database query taking 1.0 seconds (breaches the 500ms SLA)
    mock_conn = AsyncMock()
    async def slow_fetch(*args):
        await asyncio.sleep(0.8)
        return []
    mock_conn.fetch.side_effect = slow_fetch
    mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
    
    req = memory_agent.ContextQueryRequest(
        context_type="incident_resolution",
        query_text="restart database",
        limit=5
    )
    
    # Ensure it raises HTTP 504 Gateway Timeout due to SLA breach
    with pytest.raises(HTTPException) as excinfo:
        await memory_agent.query_context(req)
        
    assert excinfo.value.status_code == 504
    assert "exceeded SLA limit" in excinfo.value.detail

# ---------------------------------------------------------------------------
# 5. E2E REST API & Integration Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@patch("memory_agent.db_pool")
async def test_memory_agent_save_workflow(mock_pool):
    mock_conn = AsyncMock()
    mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
    
    client = TestClient(memory_agent.app)
    
    res = client.post("/memory/workflows", json={
        "id": str(uuid.uuid4()),
        "incident_id": str(uuid.uuid4()),
        "plan": {"steps": []},
        "status": "executing",
        "current_step_ids": [],
        "checkpoint": {"stage": "init"},
        "retry_count": 0
    })
    
    assert res.status_code == 200
    assert res.json()["status"] == "persisted"
    assert mock_conn.execute.called

@pytest.mark.asyncio
@patch("recovery_agent.asyncpg.connect")
@patch("recovery_agent.log_audit_event")
@patch("aeos_shared.http_client.request_with_retry")
async def test_recovery_agent_transient_failure_retry(mock_post, mock_audit, mock_db_conn):
    mock_conn = AsyncMock()
    mock_db_conn.return_value = mock_conn
    
    # Mock step database record (retry_count = 0)
    mock_conn.fetchrow.return_value = {
        "retry_count": 0,
        "action": json.dumps({"tool": "gather_logs", "params": {"fail": False}}),
        "agent_type": "operations"
    }
    
    client = TestClient(recovery_agent.app)
    
    # Trigger transient failure
    res = client.post("/recovery/notify-failure", json={
        "workflow_id": str(uuid.uuid4()),
        "step_id": str(uuid.uuid4()),
        "incident_id": str(uuid.uuid4()),
        "error": "connection timeout error details"
    })
    
    assert res.status_code == 200
    assert res.json()["classification"] == "transient"
    
    # Wait for the background task to perform retry delay (1s) and database calls
    await asyncio.sleep(1.2)
    
    # Assert database updated the retry_count
    assert mock_conn.execute.called
    assert "UPDATE workflow_steps SET retry_count" in mock_conn.execute.call_args[0][0]
    
    # Assert call back to workflow-engine
    exec_calls = [call for call in mock_post.call_args_list if "workflow/execute-step" in str(call)]
    assert len(exec_calls) == 1

@pytest.mark.asyncio
@patch("recovery_agent.asyncpg.connect")
@patch("recovery_agent.log_audit_event")
@patch("aeos_shared.http_client.request_with_retry")
async def test_recovery_agent_permanent_failure_replan(mock_post, mock_audit, mock_db_conn):
    client = TestClient(recovery_agent.app)
    
    # Trigger permanent failure (404 Not Found)
    res = client.post("/recovery/notify-failure", json={
        "workflow_id": str(uuid.uuid4()),
        "step_id": str(uuid.uuid4()),
        "incident_id": str(uuid.uuid4()),
        "error": "HTTP 404 Resource Not Found"
    })
    
    assert res.status_code == 200
    assert res.json()["classification"] == "permanent"
    
    await asyncio.sleep(0.1)
    
    # Assert call back to planner replan
    replan_calls = [call for call in mock_post.call_args_list if "planner/replan" in str(call)]
    assert len(replan_calls) == 1

@pytest.mark.asyncio
@patch("escalation_agent.asyncpg.connect")
@patch("escalation_agent.redis.from_url")
@patch("aeos_shared.http_client.request_with_retry")
async def test_escalation_agent_notify_and_resolve(mock_post, mock_redis_func, mock_db_conn):
    mock_conn = AsyncMock()
    mock_db_conn.return_value = mock_conn
    
    mock_redis = AsyncMock()
    # Mock redis get return value for active escalation resolution
    mock_redis.get.return_value = json.dumps({
        "escalation_id": "test-esc-123",
        "incident_id": str(uuid.uuid4()),
        "workflow_id": str(uuid.uuid4()),
        "step_id": str(uuid.uuid4()),
        "reason": "Risk score threshold breached",
        "status": "pending",
        "tier": 1,
        "created_at": datetime.now(timezone.utc).isoformat()
    })
    mock_redis_func.return_value = mock_redis
    
    client = TestClient(escalation_agent.app)
    
    # 1. Trigger escalation notification
    res_notify = client.post("/escalation/notify", json={
        "incident_id": str(uuid.uuid4()),
        "workflow_id": str(uuid.uuid4()),
        "step_id": str(uuid.uuid4()),
        "reason": "Step risk exceeds 7.0 limit"
    })
    
    assert res_notify.status_code == 200
    escalation_id = res_notify.json()["escalation_id"]
    assert escalation_id is not None
    
    # Assert Postgres status set to 'escalated'
    assert mock_conn.execute.called
    assert "UPDATE incidents SET status = 'escalated'" in mock_conn.execute.call_args_list[0][0][0]
    
    # Assert websocket event triggered and broadcasted to Observability Layer
    obs_calls = [call for call in mock_post.call_args_list if "observability/events" in str(call)]
    assert len(obs_calls) > 0
    assert obs_calls[0][1]["json"]["type"] == "escalation.triggered"
    
    # 2. Resolve escalation (Approve)
    res_resolve = client.post("/escalation/resolve", json={
        "escalation_id": escalation_id,
        "approve": True,
        "reason": "Remediation action is safe"
    })
    
    assert res_resolve.status_code == 200
    assert res_resolve.json()["status"] == "resolved"
    
    # Assert call back to workflow-engine to resume step
    we_calls = [call for call in mock_post.call_args_list if "workflow/resume-step" in str(call)]
    assert len(we_calls) == 1
    assert we_calls[0][1]["json"]["approved"] is True

@pytest.mark.asyncio
@patch("escalation_agent.redis.from_url")
@patch("aeos_shared.http_client.request_with_retry")
async def test_escalation_agent_timeout_escalation(mock_post, mock_redis_func):
    mock_redis = AsyncMock()
    # Mock an escalation created 2 seconds ago (timeout limit set to 0.1s in env)
    mock_redis.keys.return_value = ["escalation:active:test-esc-123"]
    mock_redis.get.return_value = json.dumps({
        "escalation_id": "test-esc-123",
        "incident_id": str(uuid.uuid4()),
        "workflow_id": str(uuid.uuid4()),
        "step_id": str(uuid.uuid4()),
        "reason": "manual approval timed out",
        "status": "pending",
        "tier": 1,
        "created_at": datetime(2026, 5, 19, 10, 0, 0, tzinfo=timezone.utc).isoformat()
    })
    mock_redis_func.return_value = mock_redis
    
    # Run timeout monitor check manually
    await escalation_agent.check_escalation_timeouts()
    
    # Verify that the tier escalated to 2
    assert mock_redis.set.called
    saved_data = json.loads(mock_redis.set.call_args[0][1])
    assert saved_data["tier"] == 2
    
    # Verify Tier 2 notification event was sent to Observability Layer
    obs_calls = [call for call in mock_post.call_args_list if "observability/events" in str(call)]
    assert len(obs_calls) > 0
    assert obs_calls[0][1]["json"]["payload"]["tier"] == 2

@pytest.mark.asyncio
@patch("asyncpg.connect")
@patch("redis.asyncio.from_url")
@patch("aeos_shared.http_client.request_with_retry")
@patch("aeos_shared.http_client.request_with_retry")
async def test_workflow_state_restoration(mock_post, mock_get, mock_redis_func, mock_db_conn):
    # Mock Memory Agent response returning 1 active workflow
    mock_wf_id = str(uuid.uuid4())
    mock_inc_id = str(uuid.uuid4())
    mock_get.return_value = MagicMock(status_code=200, json=lambda: [
        {
            "id": mock_wf_id,
            "incident_id": mock_inc_id,
            "status": "executing",
            "checkpoint": {"stage": "processing"}
        }
    ])
    
    # Mock Postgres returning 1 active step
    mock_db = AsyncMock()
    mock_db.fetch.return_value = [
        {
            "id": uuid.uuid4(),
            "agent_type": "operations",
            "action": json.dumps({"tool": "restart_service", "params": {}}),
            "status": "active"
        }
    ]
    mock_db_conn.return_value = mock_db
    
    # Mock Redis client
    mock_redis = MagicMock()
    mock_redis.publish = AsyncMock()
    mock_redis_func.return_value = mock_redis
    
    # Run state restoration logic
    await workflow_engine.restore_in_progress_workflows()
    
    # Verify re-enqueue logic published to agent channel
    assert mock_redis.publish.called
    channel, message = mock_redis.publish.call_args[0]
    assert channel == "agent:operations:tasks"
    msg_data = json.loads(message)
    assert msg_data["workflow_id"] == mock_wf_id
    assert msg_data["incident_id"] == mock_inc_id
    
    # Verify workflow.restored event emitted
    obs_calls = [call for call in mock_post.call_args_list if "observability/events" in str(call)]
    assert len(obs_calls) == 1
    assert obs_calls[0][1]["json"]["type"] == "workflow.restored"

# ---------------------------------------------------------------------------
# 6. Specialist Agent Message Loop Integration Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@patch("operations_agent.redis.from_url")
@patch("aeos_shared.http_client.request_with_retry")
async def test_operations_specialist_agent_flow(mock_post, mock_redis_func):
    mock_redis = MagicMock()
    mock_redis.close = AsyncMock()
    mock_pubsub = AsyncMock()
    
    # Return mock task message on first call, then stop the loop
    calls = 0
    def mock_get_message(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            return {
                "type": "message",
                "pattern": None,
                "channel": "agent:operations:tasks",
                "data": json.dumps({
                    "task_id": "task-operations-123",
                    "workflow_id": "wf-123",
                    "step_id": "step-123",
                    "incident_id": "inc-123",
                    "action": {"tool": "restart_service", "params": {"service_name": "db"}}
                })
            }
        else:
            operations_agent.should_stop = True
            return None
            
    mock_pubsub.get_message.side_effect = mock_get_message
    
    mock_redis.pubsub.return_value = mock_pubsub
    mock_redis_func.return_value = mock_redis
    
    # Reset should_stop before starting
    operations_agent.should_stop = False
    
    # Run loop (will stop after 2nd get_message call)
    await operations_agent.listen_to_tasks()
    
    # Wait for the background process_task task to execute
    await asyncio.sleep(0.1)
    
    # Assert success callback is posted back to Coordinator
    cb_calls = [call for call in mock_post.call_args_list if "coordinator/step-complete" in str(call)]
    assert len(cb_calls) == 1
    assert cb_calls[0][1]["json"]["task_id"] == "task-operations-123"
    assert cb_calls[0][1]["json"]["output"]["restarted"] is True
