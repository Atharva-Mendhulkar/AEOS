import os
import sys
import uuid
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

os.environ["GEMINI_API_KEY"] = "mock-key"
os.environ["CELERY_ALWAYS_EAGER"] = "True"
os.environ["DATABASE_URL"] = "postgresql://postgres:postgres@localhost:5432/aeos"
os.environ["REDIS_URL"] = "redis://localhost:6379/0"

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
sys.path.insert(0, os.path.join(BASE_DIR, "shared/python"))
sys.path.insert(0, os.path.join(BASE_DIR, "services/planner-agent"))
sys.path.insert(0, os.path.join(BASE_DIR, "services/workflow-engine"))

import importlib.util
def load_module(module_name, file_path):
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module

planner_agent = load_module("planner_agent", os.path.join(BASE_DIR, "services/planner-agent/main.py"))
workflow_engine = load_module("workflow_engine", os.path.join(BASE_DIR, "services/workflow-engine/main.py"))

@pytest.fixture(autouse=True)
def mock_redis_lock():
    with patch("workflow_engine.redis_async.from_url", new_callable=MagicMock) as mock_from_url:
        mock_conn = MagicMock()
        async def fake_set(*args, **kwargs):
            return True
        mock_conn.set = fake_set
        async def fake_delete(*args, **kwargs):
            return True
        mock_conn.delete = fake_delete
        async def fake_aclose(*args, **kwargs):
            pass
        mock_conn.aclose = fake_aclose
        mock_from_url.return_value = mock_conn
        yield mock_conn



from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Planner Agent Tests
# ---------------------------------------------------------------------------

def test_validate_plan_structure_acyclic():
    # Acyclic graph: 1 -> 2 -> 3
    steps = [
        {"id": "1", "depends_on": []},
        {"id": "2", "depends_on": ["1"]},
        {"id": "3", "depends_on": ["2"]}
    ]
    assert planner_agent.validate_plan_structure(steps) is True

def test_validate_plan_structure_cyclic():
    # Cyclic graph: 1 -> 2 -> 3 -> 1
    steps = [
        {"id": "1", "depends_on": ["3"]},
        {"id": "2", "depends_on": ["1"]},
        {"id": "3", "depends_on": ["2"]}
    ]
    assert planner_agent.validate_plan_structure(steps) is False

def test_validate_plan_structure_missing_dep():
    # Step depends on non-existent step
    steps = [
        {"id": "1", "depends_on": ["99"]}
    ]
    assert planner_agent.validate_plan_structure(steps) is False

@patch("aeos_shared.http_client.request_with_retry")
def test_planner_generate_success(mock_post):
    # Mocking external calls (Governance validates, Memory persists, Coordinator routes)
    mock_post.return_value = MagicMock(
        status_code=200,
        json=lambda: {"valid": True, "violations": [], "status": "executing"}
    )
    
    client = TestClient(planner_agent.app)
    response = client.post(
        "/planner/generate",
        json={
            "incident_id": str(uuid.uuid4()),
            "severity": "high",
            "root_signature": "signature-123",
            "workflow_id": str(uuid.uuid4())
        }
    )
    
    assert response.status_code == 200
    assert response.json()["status"] == "success"
    steps = response.json()["steps"]
    assert len(steps) == 3
    # Check topological order is validated and returns valid response
    assert steps[1]["depends_on"] == [steps[0]["id"]]

@patch("aeos_shared.http_client.request_with_retry")
def test_planner_governance_retry_and_escalate(mock_post):
    # Mock Governance validate-plan returns invalid: True (violations found)
    mock_post.return_value = MagicMock(
        status_code=200,
        json=lambda: {"valid": False, "violations": [{"message": "Violates policy GP-2"}]}
    )
    
    client = TestClient(planner_agent.app)
    response = client.post(
        "/planner/generate",
        json={
            "incident_id": str(uuid.uuid4()),
            "severity": "high",
            "root_signature": "signature-123",
            "workflow_id": str(uuid.uuid4())
        }
    )
    
    # Exceeds retry limit (3 attempts), escalates and returns 422
    assert response.status_code == 422
    # Ensure escalation agent was notified
    escalation_call = [call for call in mock_post.call_args_list if "escalation" in str(call)]
    assert len(escalation_call) > 0

# ---------------------------------------------------------------------------
# Workflow Engine Tests
# ---------------------------------------------------------------------------

@patch("aeos_shared.http_client.request_with_retry")
def test_workflow_execute_step_low_risk(mock_post):
    # Mock Governance validate-action returns low risk score (5.0, approved)
    # Mock Coordinator step-complete is called
    mock_post.return_value = MagicMock(
        status_code=200,
        json=lambda: {"risk_score": 5.0, "approved": True}
    )
    
    client = TestClient(workflow_engine.app)
    response = client.post(
        "/workflow/execute-step",
        json={
            "task_id": str(uuid.uuid4()),
            "workflow_id": str(uuid.uuid4()),
            "step_id": str(uuid.uuid4()),
            "incident_id": str(uuid.uuid4()),
            "action": {
                "tool": "gather_logs",
                "params": {"service": "db"},
                "timeout_seconds": 30
            }
        }
    )
    
    assert response.status_code == 200
    assert response.json()["status"] == "executing"
    # Ensure tool execution publishes step-complete callback to Coordinator
    complete_call = [call for call in mock_post.call_args_list if "step-complete" in str(call)]
    assert len(complete_call) > 0

@patch("asyncpg.connect", new_callable=MagicMock)
@patch("aeos_shared.http_client.request_with_retry", new_callable=MagicMock)
def test_workflow_execute_step_high_risk_suspends(mock_post, mock_db):
    async def fake_post(*args, **kwargs):
        return MagicMock(status_code=200, json=lambda: {"risk_score": 8.0, "approved": True})
    mock_post.side_effect = fake_post
    
    # Mock asyncpg connection
    mock_conn = AsyncMock()
    async def fake_connect(*args, **kwargs):
        return mock_conn
    mock_db.side_effect = fake_connect
    client = TestClient(workflow_engine.app)
    response = client.post(
        "/workflow/execute-step",
        json={
            "task_id": str(uuid.uuid4()),
            "workflow_id": str(uuid.uuid4()),
            "step_id": str(uuid.uuid4()),
            "incident_id": str(uuid.uuid4()),
            "action": {
                "tool": "restart_service",
                "params": {"service_name": "db"},
                "timeout_seconds": 30
            }
        }
    )
    
    assert response.status_code == 200
    assert response.json()["status"] == "suspended"
    assert response.json()["risk_score"] == 8.0
    
    # Ensure Escalation Agent is notified
    escalate_call = [call for call in mock_post.call_args_list if "escalation" in str(call)]
    assert len(escalate_call) > 0
    # Ensure DB is updated to set status to suspended
    assert mock_conn.execute.called

@patch("aeos_shared.http_client.request_with_retry", new_callable=MagicMock)
def test_workflow_execute_step_critical_risk_halts(mock_post):
    async def fake_post(*args, **kwargs):
        return MagicMock(status_code=200, json=lambda: {"risk_score": 9.5, "approved": False})
    mock_post.side_effect = fake_post

    client = TestClient(workflow_engine.app)
    response = client.post(
        "/workflow/execute-step",
        json={
            "task_id": str(uuid.uuid4()),
            "workflow_id": str(uuid.uuid4()),
            "step_id": str(uuid.uuid4()),
            "incident_id": str(uuid.uuid4()),
            "action": {
                "tool": "restart_service",
                "params": {"service_name": "db"},
                "timeout_seconds": 30
            }
        }
    )
    
    assert response.status_code == 200
    assert response.json()["status"] == "halted"
    # Ensure Coordinator is notified of step failure
    fail_call = [call for call in mock_post.call_args_list if "step-failed" in str(call)]
    assert len(fail_call) > 0
