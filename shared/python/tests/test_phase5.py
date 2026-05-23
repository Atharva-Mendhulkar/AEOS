import os
import sys
import json
import uuid
import pytest
import asyncio
import hashlib
from datetime import datetime, timezone
from unittest.mock import MagicMock, AsyncMock, patch

from jose import jwt
from fastapi.testclient import TestClient
from socketio.exceptions import ConnectionRefusedError
import socketio

# Setup paths and environment variables
os.environ["GEMINI_API_KEY"] = "mock-key"
os.environ["DATABASE_URL"] = "postgresql://postgres:postgres@localhost:5432/aeos"
os.environ["REDIS_URL"] = "redis://localhost:6379/0"
os.environ["AEOS_JWT_SECRET"] = "test-secret-key-for-testing"

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
sys.path.insert(0, os.path.join(BASE_DIR, "shared/python"))
sys.path.insert(0, os.path.join(BASE_DIR, "services/observability-service"))

import importlib.util
def load_module(module_name, file_path):
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module

obs_service = load_module("obs_service", os.path.join(BASE_DIR, "services/observability-service/main.py"))

# Helper to compute entries hashes
from jobs.chain_validator import compute_entry_hash, make_canonical_dict

# ---------------------------------------------------------------------------
# 1. JWT Authentication Handshake Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_websocket_jwt_handshake_missing_token():
    # Test connection rejection when token is missing
    environ = {"QUERY_STRING": ""}
    with pytest.raises(ConnectionRefusedError) as exc_info:
        await obs_service.connect("sid_123", environ)
    assert "Missing authentication token" in str(exc_info.value)

@pytest.mark.asyncio
async def test_websocket_jwt_handshake_invalid_token():
    # Test connection rejection when token is invalid
    environ = {"QUERY_STRING": "token=invalid-jwt-token"}
    with pytest.raises(ConnectionRefusedError) as exc_info:
        await obs_service.connect("sid_123", environ)
    assert "Invalid authentication token" in str(exc_info.value)

@pytest.mark.asyncio
async def test_websocket_jwt_handshake_success():
    # Test successful handshake with valid JWT containing exp and iat
    import time
    now = int(time.time())
    token = jwt.encode(
        {
            "sub": "operator",
            "role": "operator",
            "iat": now,
            "exp": now + 3600
        },
        "test-secret-key-for-testing",
        algorithm="HS256"
    )
    environ = {"QUERY_STRING": f"token={token}"}
    
    # Mock save_session
    obs_service.sio.save_session = AsyncMock()
    
    await obs_service.connect("sid_123", environ)
    obs_service.sio.save_session.assert_called_once()
    saved_session = obs_service.sio.save_session.call_args[0][1]
    assert saved_session["user"]["sub"] == "operator"

# ---------------------------------------------------------------------------
# 2. Redis Event Buffering and Reconnection Replay Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@patch("obs_service.redis.from_url")
async def test_reconnection_replay_on_subscribe(mock_redis_func):
    mock_redis = MagicMock()
    mock_redis.close = AsyncMock()
    
    # ZRANGEBYSCORE mock data (sequence 2 and 3)
    mock_events = [
        json.dumps({"workflow_id": "wf-123", "event_type": "step.started", "sequence": 2}),
        json.dumps({"workflow_id": "wf-123", "event_type": "step.completed", "sequence": 3}),
    ]
    mock_redis.zrangebyscore = AsyncMock(return_value=mock_events)
    mock_redis_func.return_value = mock_redis
    
    obs_service.sio.enter_room = AsyncMock()
    obs_service.sio.emit = AsyncMock()
    
    data = {"workflow_id": "wf-123", "last_sequence": 1}
    result = await obs_service.handle_subscribe("sid_123", data)
    
    assert result["status"] == "subscribed"
    assert result["replayed"] == 2
    
    # Verify client joined Socket.IO room
    obs_service.sio.enter_room.assert_called_with("sid_123", "wf-123")
    
    # Verify correct range queried from Redis
    mock_redis.zrangebyscore.assert_called_with("observability:buffer:wf-123", min=2, max="+inf")
    
    # Verify replayed events emitted to the client
    assert obs_service.sio.emit.call_count == 2
    emitted_event_1 = obs_service.sio.emit.call_args_list[0][0][1]
    assert emitted_event_1["sequence"] == 2
    assert emitted_event_1["event_type"] == "step.started"

# ---------------------------------------------------------------------------
# 3. Event Ingestion, Broadcasting and SLA latency checking
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@patch("obs_service.redis.from_url")
@patch("httpx.AsyncClient.post")
async def test_event_ingestion_and_broadcast_sla(mock_post, mock_redis_func):
    # Setup mocks
    mock_redis = MagicMock()
    mock_redis.incr = AsyncMock(return_value=12)
    mock_redis.zadd = AsyncMock()
    mock_redis.zremrangebyrank = AsyncMock()
    mock_redis.expire = AsyncMock()
    mock_redis.close = AsyncMock()
    mock_redis_func.return_value = mock_redis
    
    # Memory Agent audit log mock
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"status": "audited", "prev_entry_hash": "some_prev_hash"}
    mock_post.return_value = mock_resp
    
    obs_service.sio.emit = AsyncMock()
    
    event_payload = {
        "event_type": "step.started",
        "agent_identity": "operations",
        "incident_id": "inc-123",
        "workflow_id": "wf-123",
        "action_description": "Starting db recovery",
        "inputs": {"service": "db"},
        "outputs": None,
        "risk_score": 5.0
    }
    
    response = await obs_service.ingest_event(event_payload)
    
    assert response["status"] == "processed"
    assert response["sequence"] == 12
    
    # Verify post to Memory Agent
    mock_post.assert_called_once()
    assert "/memory/audit" in str(mock_post.call_args[0][0])
    
    # Verify broadcast room emission in Socket.IO
    obs_service.sio.emit.assert_called_once()
    room_arg = obs_service.sio.emit.call_args[1]["room"]
    assert room_arg == "wf-123"

# ---------------------------------------------------------------------------
# 4. Audit Trail Chain Tamper-Evidence Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@patch("asyncpg.connect")
async def test_audit_trail_chain_validation_valid(mock_connect):
    mock_conn = AsyncMock()
    
    # Create valid chain entries
    entry1 = {
        "event_type": "step.started",
        "timestamp": datetime.now(timezone.utc),
        "agent_identity": "operations",
        "incident_id": uuid.uuid4(),
        "workflow_id": uuid.uuid4(),
        "action_description": "start",
        "inputs": {},
        "outputs": {},
        "risk_score": 1.0,
        "prev_entry_hash": "genesis"
    }
    hash1 = compute_entry_hash(entry1)
    
    entry2 = {
        "event_type": "step.completed",
        "timestamp": datetime.now(timezone.utc),
        "agent_identity": "operations",
        "incident_id": entry1["incident_id"],
        "workflow_id": entry1["workflow_id"],
        "action_description": "complete",
        "inputs": {},
        "outputs": {},
        "risk_score": 1.0,
        "prev_entry_hash": hash1
    }
    hash2 = compute_entry_hash(entry2)
    
    rows = [
        {"id": 1, **entry1},
        {"id": 2, **entry2}
    ]
    mock_conn.fetch.return_value = rows
    mock_connect.return_value = mock_conn
    
    result = await obs_service.trigger_chain_validation()
    assert result["status"] == "valid"
    assert result["validated_count"] == 2

@pytest.mark.asyncio
@patch("asyncpg.connect")
async def test_audit_trail_chain_validation_tampered(mock_connect):
    mock_conn = AsyncMock()
    
    # Create tampered chain entries (mismatched prev_entry_hash)
    entry1 = {
        "event_type": "step.started",
        "timestamp": datetime.now(timezone.utc),
        "agent_identity": "operations",
        "incident_id": uuid.uuid4(),
        "workflow_id": uuid.uuid4(),
        "action_description": "start",
        "inputs": {},
        "outputs": {},
        "risk_score": 1.0,
        "prev_entry_hash": "genesis"
    }
    
    entry2 = {
        "event_type": "step.completed",
        "timestamp": datetime.now(timezone.utc),
        "agent_identity": "operations",
        "incident_id": entry1["incident_id"],
        "workflow_id": entry1["workflow_id"],
        "action_description": "complete",
        "inputs": {},
        "outputs": {},
        "risk_score": 1.0,
        "prev_entry_hash": "incorrect_previous_hash_link"
    }
    
    rows = [
        {"id": 1, **entry1},
        {"id": 2, **entry2}
    ]
    mock_conn.fetch.return_value = rows
    mock_connect.return_value = mock_conn
    
    result = await obs_service.trigger_chain_validation()
    assert result["status"] == "tampered"
    assert result["compromised_id"] == 2

# ---------------------------------------------------------------------------
# 5. Execution Trace Completeness Checker Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@patch("asyncpg.connect")
async def test_execution_trace_completeness_valid(mock_connect):
    mock_conn = AsyncMock()
    
    wf_id = uuid.uuid4()
    step_id = uuid.uuid4()
    
    # Mock workflow row
    mock_conn.fetchrow.return_value = {
        "id": wf_id,
        "incident_id": uuid.uuid4(),
        "plan": {"steps": []},
        "status": "completed",
        "current_step_ids": [],
        "checkpoint": {},
        "retry_count": 0,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc)
    }
    
    # Mock step row
    mock_conn.fetch.side_effect = [
        [
            {
                "id": step_id,
                "workflow_id": wf_id,
                "agent_type": "operations",
                "action": {"tool": "restart"},
                "status": "completed",
                "depends_on": [],
                "output": {"status": "success"},
                "retry_count": 0,
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc)
            }
        ],
        [
            {
                "id": 1,
                "event_type": "step.started",
                "timestamp": datetime.now(timezone.utc),
                "agent_identity": "operations",
                "incident_id": uuid.uuid4(),
                "workflow_id": wf_id,
                "action_description": "Executing step",
                "inputs": {"step_id": str(step_id)},
                "outputs": None,
                "risk_score": 1.0
            }
        ]
    ]
    
    mock_connect.return_value = mock_conn
    
    result = await obs_service.get_workflow_trace(str(wf_id))
    assert result["workflow"]["status"] == "completed"
    assert len(result["steps"]) == 1
    assert result["completeness_warning"] is None

@pytest.mark.asyncio
@patch("asyncpg.connect")
async def test_execution_trace_completeness_missing_elements(mock_connect):
    mock_conn = AsyncMock()
    wf_id = uuid.uuid4()
    
    mock_conn.fetchrow.return_value = {
        "id": wf_id,
        "incident_id": uuid.uuid4(),
        "plan": {"steps": []},
        "status": "completed",
        "current_step_ids": [],
        "checkpoint": {},
        "retry_count": 0,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc)
    }
    
    # Return empty steps and empty audit logs
    mock_conn.fetch.side_effect = [[], []]
    mock_connect.return_value = mock_conn
    
    result = await obs_service.get_workflow_trace(str(wf_id))
    assert result["completeness_warning"] is not None
    assert "Missing components" in result["completeness_warning"]
