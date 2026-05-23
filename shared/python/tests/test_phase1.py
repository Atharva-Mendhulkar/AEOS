import os
import sys
import uuid
import json
import pytest
import importlib.util
from datetime import datetime, timezone
from unittest.mock import MagicMock, AsyncMock, patch

# Ensure environment variables are set before importing
os.environ["AEOS_JWT_SECRET"] = "test-secret-key-for-testing"
os.environ["DATABASE_URL"] = "postgresql://postgres:postgres@localhost:5432/aeos"
os.environ["REDIS_URL"] = "redis://localhost:6379/0"
os.environ["SPEECHMATICS_API_KEY"] = "mock-key"
os.environ["GEMINI_API_KEY"] = "mock-key"

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
sys.path.insert(0, os.path.join(BASE_DIR, "shared/python"))
sys.path.insert(0, os.path.join(BASE_DIR, "services/api-gateway"))
sys.path.insert(0, os.path.join(BASE_DIR, "services/incident-analysis-agent"))

# Dynamically load the modules to avoid main.py namespace collisions
def load_module(module_name, file_path):
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module

# We patch db connection initialization before loading modules so they don't block
with patch("aeos_shared.db.init_db_pool", new_callable=AsyncMock):
    api_gateway = load_module("api_gateway", os.path.join(BASE_DIR, "services/api-gateway/main.py"))
    incident_agent = load_module("incident_agent", os.path.join(BASE_DIR, "services/incident-analysis-agent/main.py"))

from fastapi.testclient import TestClient
from jose import jwt
from aeos_shared.auth.jwt_auth import ALGORITHM

# Helper to generate test JWT
def get_auth_headers(role: str = "admin") -> dict:
    now = int(datetime.now(timezone.utc).timestamp())
    payload = {
        "sub": "test-user",
        "role": role,
        "exp": now + 3600,
        "iat": now
    }
    token = jwt.encode(payload, os.environ["AEOS_JWT_SECRET"], algorithm=ALGORITHM)
    return {"Authorization": f"Bearer {token}"}

# ---------------------------------------------------------------------------
# API Gateway Tests
# ---------------------------------------------------------------------------

def test_ingest_auth_failure():
    client = TestClient(api_gateway.app)
    response = client.post(
        "/api/v1/incidents/ingest",
        data={"format": "text", "raw_content": "test warning"}
    )
    assert response.status_code == 401
    assert "Authorization header missing or invalid scheme" in response.json()["error"]["message"]

@patch("httpx.AsyncClient.post", new_callable=AsyncMock)
def test_ingest_unsupported_format(mock_post):
    # Mock DB Connection
    mock_conn = AsyncMock()
    
    # Override get_db dependency
    from aeos_shared import get_db
    api_gateway.app.dependency_overrides[get_db] = lambda: mock_conn
    
    client = TestClient(api_gateway.app)
    headers = get_auth_headers()
    response = client.post(
        "/api/v1/incidents/ingest",
        headers=headers,
        data={"format": "xml", "raw_content": "<xml></xml>"}
    )
    
    assert response.status_code == 422
    assert "Unsupported format" in response.json()["error"]["message"]
    # Check that it tried to audit the format rejection
    assert mock_post.called
    audit_call_args = mock_post.call_args[1]["json"]
    assert audit_call_args["event_type"] == "format.rejected"

def test_ingest_oversized_file():
    client = TestClient(api_gateway.app)
    headers = get_auth_headers()
    
    oversized_content = "x" * (51 * 1024 * 1024)
    response = client.post(
        "/api/v1/incidents/ingest",
        headers=headers,
        data={"format": "text", "raw_content": oversized_content}
    )
    
    assert response.status_code == 413
    assert "exceeds maximum limit" in response.json()["error"]["message"]

@patch("httpx.AsyncClient.post", new_callable=AsyncMock)
def test_ingest_text_success(mock_post):
    mock_conn = AsyncMock()
    mock_conn.execute = AsyncMock()
    
    from aeos_shared import get_db
    api_gateway.app.dependency_overrides[get_db] = lambda: mock_conn
    
    client = TestClient(api_gateway.app)
    headers = get_auth_headers()
    response = client.post(
        "/api/v1/incidents/ingest",
        headers=headers,
        data={"format": "text", "raw_content": "critical database error detected"}
    )
    
    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert "incident_id" in response.json()
    
    # Verify DB insert was called
    assert mock_conn.execute.called
    # Verify it posted immediately to Coordinator
    assert mock_post.called
    assert "coordinator" in mock_post.call_args[0][0]

@patch("api_gateway.transcribe_audio", new_callable=AsyncMock)
def test_ingest_audio_preprocessing_trigger(mock_transcribe):
    mock_conn = AsyncMock()
    mock_conn.execute = AsyncMock()
    
    from aeos_shared import get_db
    api_gateway.app.dependency_overrides[get_db] = lambda: mock_conn
    
    client = TestClient(api_gateway.app)
    headers = get_auth_headers()
    
    # Send a tiny mock audio file
    response = client.post(
        "/api/v1/incidents/ingest",
        headers=headers,
        data={"format": "audio"},
        files={"file": ("test.wav", b"riff-wave-data", "audio/wav")}
    )
    
    assert response.status_code == 200
    assert response.json()["status"] == "pending"

# ---------------------------------------------------------------------------
# Incident Analysis Agent Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_incident_analysis_agent_mock_classification():
    res_critical = await incident_agent.process_classification("This is a critical system warning.")
    assert res_critical["severity"] == "critical"
    assert res_critical["confidence_score"] == 0.95
    assert res_critical["root_signature"] == "CRITICAL_ALERT"
    
    res_ambiguous = await incident_agent.process_classification("This input is very ambiguous.")
    assert res_ambiguous["confidence_score"] == 0.50
    assert res_ambiguous["root_signature"] == "AMBIGUOUS_INPUT"
