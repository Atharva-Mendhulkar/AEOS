import os
import sys
import json
import uuid
import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch

os.environ["GEMINI_API_KEY"] = "mock-key"
os.environ["DATABASE_URL"] = "postgresql://postgres:postgres@localhost:5432/aeos"
os.environ["REDIS_URL"] = "redis://localhost:6379/0"

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
sys.path.insert(0, os.path.join(BASE_DIR, "shared/python"))
sys.path.insert(0, os.path.join(BASE_DIR, "services/governance-service"))

import importlib.util
def load_module(module_name, file_path):
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module

gov_service = load_module("gov_service", os.path.join(BASE_DIR, "services/governance-service/main.py"))

from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# 1. Rule-Based Scoring Engine Tests
# ---------------------------------------------------------------------------

def test_rule_based_risk_base_scores():
    # Database Write
    a1 = {"tool": "delete_table", "params": {"action_type": "database write"}}
    res1 = gov_service.evaluate_rule_based_risk(a1)
    assert res1.score == 6.0
    
    # Read-only
    a2 = {"tool": "gather_logs", "params": {}} # Infers read-only
    res2 = gov_service.evaluate_rule_based_risk(a2)
    assert res2.score == 2.0
    
    # Unknown fallback
    a3 = {"tool": "novel_tool", "params": {}}
    res3 = gov_service.evaluate_rule_based_risk(a3)
    assert res3.score == 5.0

def test_rule_based_risk_modifiers():
    # Base 6.0 + production 2.0 = 8.0
    a1 = {"tool": "insert_row", "params": {"action_type": "database write", "scope": "production"}}
    res1 = gov_service.evaluate_rule_based_risk(a1)
    assert res1.score == 8.0
    
    # Base 2.0 + production 2.0 + sensitive 1.5 + irreversible 1.0 = 6.5
    a2 = {
        "tool": "read_records",
        "params": {
            "action_type": "read-only queries",
            "scope": "production",
            "data_sensitivity": "sensitive",
            "irreversible": True
        }
    }
    res2 = gov_service.evaluate_rule_based_risk(a2)
    assert res2.score == 6.5

    # Cap at 10.0 check
    a3 = {
        "tool": "delete_db",
        "params": {
            "action_type": "database write",
            "scope": "production",
            "data_sensitivity": "sensitive",
            "irreversible": True
        }
    }
    res3 = gov_service.evaluate_rule_based_risk(a3)
    assert res3.score == 10.0

# ---------------------------------------------------------------------------
# 2. LLM-Based Scoring Engine Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@patch("scoring.llm_based.get_redis_client")
async def test_llm_based_risk_scoring(mock_redis_client):
    # Mock redis client cache miss
    mock_redis = AsyncMock()
    mock_redis.get.return_value = None
    mock_redis_client.return_value = mock_redis
    
    action = {"tool": "critical_task", "params": {}}
    
    res = await gov_service.evaluate_llm_risk(action, "operations")
    assert res.score == 9.2 # Returns mock score for database/critical keyword
    assert mock_redis.setex.called

    # Mock cache hit
    mock_redis.get.return_value = json.dumps({"score": 4.5, "factors": ["Cache Hit Factors"]})
    res_hit = await gov_service.evaluate_llm_risk(action, "operations")
    assert res_hit.score == 4.5
    assert res_hit.factors == ["Cache Hit Factors"]

# ---------------------------------------------------------------------------
# 3. Permission Enforcement Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@patch("permissions.enforcer.get_permissions_for_agent")
async def test_permission_enforcement(mock_get_perms):
    # Setup mock permissions: operations can restart staging/prod services, but not secret resources
    mock_get_perms.return_value = {
        "allowed_resources": ["db_*", "api_*"],
        "denied_resources": ["db_secret"],
        "allowed_tools": ["restart_service", "gather_logs"],
        "denied_tools": []
    }
    
    # Tool not allowed
    a1 = {"tool": "delete_table", "params": {"resource": "db_users"}}
    res1 = await gov_service.check_permission("operations", a1)
    assert res1.allowed is False
    assert "Tool 'delete_table' is not in allowed_tools" in res1.reason

    # Resource not allowed
    a2 = {"tool": "restart_service", "params": {"resource": "other_service"}}
    res2 = await gov_service.check_permission("operations", a2)
    assert res2.allowed is False
    assert "Resource 'other_service' is not in allowed_resources" in res2.reason

    # Denied resource
    a3 = {"tool": "restart_service", "params": {"resource": "db_secret"}}
    res3 = await gov_service.check_permission("operations", a3)
    assert res3.allowed is False
    assert "Resource 'db_secret' matches denied_resources" in res3.reason

    # Allowed resource
    a4 = {"tool": "restart_service", "params": {"resource": "db_users"}}
    res4 = await gov_service.check_permission("operations", a4)
    assert res4.allowed is True

# ---------------------------------------------------------------------------
# 4. Policy Configuration Validation Tests
# ---------------------------------------------------------------------------

def test_policy_config_schema_validation():
    from fastapi import HTTPException
    # Valid configurations should not raise any exceptions
    gov_service.validate_policy_json("permission", {
        "agent_type": "operations",
        "allowed_resources": ["db_*"]
    })
    
    gov_service.validate_policy_json("anomaly", {
        "max_frequency_per_minute": 50,
        "max_consecutive_identical_actions": 5
    })
    
    gov_service.validate_policy_json("risk_threshold", {
        "suspend_threshold": 7.0,
        "halt_threshold": 9.0
    })

    gov_service.validate_policy_json("retention", {
        "retention_days": 90
    })

    # Invalid configurations should raise 422 HTTPException
    with pytest.raises(HTTPException) as exc1:
        gov_service.validate_policy_json("permission", {
            "allowed_resources": ["db_*"] # Missing agent_type
        })
    assert exc1.value.status_code == 422

    with pytest.raises(HTTPException) as exc2:
        gov_service.validate_policy_json("anomaly", {
            "max_frequency_per_minute": -10 # Negative frequency
        })
    assert exc2.value.status_code == 422

    with pytest.raises(HTTPException) as exc3:
        gov_service.validate_policy_json("risk_threshold", {
            "suspend_threshold": 8.5,
            "halt_threshold": 8.0 # Suspend exceeds Halt
        })
    assert exc3.value.status_code == 422

    with pytest.raises(HTTPException) as exc4:
        gov_service.validate_policy_json("invalid_type", {})
    assert exc4.value.status_code == 422

# ---------------------------------------------------------------------------
# 5. Anomaly Detection Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@patch("anomaly.detector.get_redis_client")
@patch("anomaly.detector.get_anomaly_policy")
@patch("httpx.AsyncClient.post")
async def test_anomaly_detection_limits(mock_post, mock_policy, mock_redis_client):
    # Setup mock policy limits
    mock_policy.return_value = {
        "max_frequency_per_minute": 2,
        "max_consecutive_identical_actions": 2,
        "frequency_time_window_seconds": 60
    }
    
    mock_redis = AsyncMock()
    mock_redis_client.return_value = mock_redis
    
    # 1. Frequency limit breach
    # Redis returns 3 recent events in the window
    mock_redis.lrange.return_value = [
        json.dumps({"timestamp": 100.0, "tool": "restart", "resource": "db"}),
        json.dumps({"timestamp": 98.0, "tool": "restart", "resource": "db"}),
        json.dumps({"timestamp": 96.0, "tool": "restart", "resource": "db"}),
    ]
    with patch("time.time", return_value=101.0):
        anomaly = await gov_service.record_action_and_detect_anomalies("operations", {"tool": "restart", "params": {"resource": "db"}})
        assert anomaly is not None
        assert anomaly["pattern_id"] == "FREQ_EXCEEDED"
        # Check Observability notification called
        obs_call = [call for call in mock_post.call_args_list if "observability" in str(call)]
        assert len(obs_call) > 0

    # 2. Loop repetition limit breach
    # Reset mock post calls
    mock_post.reset_mock()
    # Redis returns 3 consecutive identical events but times are scattered (no frequency breach)
    mock_redis.lrange.return_value = [
        json.dumps({"timestamp": 100.0, "tool": "restart", "resource": "db"}),
        json.dumps({"timestamp": 50.0, "tool": "restart", "resource": "db"}),
        json.dumps({"timestamp": 10.0, "tool": "restart", "resource": "db"}),
    ]
    with patch("time.time", return_value=101.0):
        anomaly2 = await gov_service.record_action_and_detect_anomalies("operations", {"tool": "restart", "params": {"resource": "db"}})
        assert anomaly2 is not None
        assert anomaly2["pattern_id"] == "LOOP_DETECTED"
        obs_call2 = [call for call in mock_post.call_args_list if "observability" in str(call)]
        assert len(obs_call2) > 0

# ---------------------------------------------------------------------------
# 6. Governance Service Web API Gating Verification
# ---------------------------------------------------------------------------

@patch("asyncpg.connect")
@patch("permissions.enforcer.get_permissions_for_agent")
@patch("gov_service.record_audit_entry")
def test_web_api_validate_action_execution_gates(mock_audit, mock_get_perms, mock_db):
    client = TestClient(gov_service.app)

    # 1. Allowed (Approved < 7.0)
    mock_get_perms.return_value = {"allowed_tools": ["gather_logs"]}
    res1 = client.post("/governance/validate-action", json={
        "action": {"tool": "gather_logs", "params": {}},
        "agent_type": "operations"
    })
    assert res1.status_code == 200
    assert res1.json()["status"] == "executing"
    assert res1.json()["approved"] is True

    # 2. Suspended (Approval Gate 7.0–8.9)
    # Database write (6.0) + production scope (+2.0) = 8.0 risk score
    mock_get_perms.return_value = {"allowed_tools": ["delete_table"]}
    res2 = client.post("/governance/validate-action", json={
        "action": {"tool": "delete_table", "params": {"action_type": "database write", "scope": "production"}},
        "agent_type": "operations"
    })
    assert res2.status_code == 200
    assert res2.json()["status"] == "suspended"
    assert res2.json()["risk_score"] == 8.0

    # 3. Halted (Circuit Breaker >= 9.0)
    # Database write (6.0) + production (+2.0) + sensitive (+1.5) = 9.5
    res3 = client.post("/governance/validate-action", json={
        "action": {
            "tool": "delete_table",
            "params": {"action_type": "database write", "scope": "production", "data_sensitivity": "sensitive"}
        },
        "agent_type": "operations"
    })
    assert res3.status_code == 200
    assert res3.json()["status"] == "halted"
    assert res3.json()["approved"] is False

    # 4. Denied (Permission check rejection)
    mock_get_perms.return_value = {"allowed_tools": ["gather_logs"]}
    res4 = client.post("/governance/validate-action", json={
        "action": {"tool": "unauthorized_command"},
        "agent_type": "operations"
    })
    assert res4.status_code == 200
    assert res4.json()["status"] == "denied"
    assert res4.json()["approved"] is False
    assert "GOVERNANCE_PERMISSION_DENIED" in res4.json()["factors"][0]
