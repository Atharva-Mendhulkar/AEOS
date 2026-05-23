import os
import sys
import time
import json
import logging
from datetime import datetime
import asyncio
from typing import Optional, Dict, Any
from urllib.parse import parse_qs

from fastapi import FastAPI, Request, HTTPException, Query
import httpx
import redis.asyncio as redis
import socketio
from socketio.exceptions import ConnectionRefusedError

import importlib.util

# Load trace builder safely to avoid stdlib trace collision
try:
    # Try importing directly
    sys_path_save = sys.path[:]
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from trace.builder import build_execution_trace
    sys.path = sys_path_save
except (ImportError, AttributeError, ModuleNotFoundError):
    spec = importlib.util.spec_from_file_location(
        "obs_trace_builder", 
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "trace", "builder.py")
    )
    obs_trace_builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obs_trace_builder)
    build_execution_trace = obs_trace_builder.build_execution_trace

# Load chain validator safely
try:
    sys_path_save = sys.path[:]
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from jobs.chain_validator import validate_chain
    sys.path = sys_path_save
except (ImportError, AttributeError, ModuleNotFoundError):
    spec = importlib.util.spec_from_file_location(
        "obs_chain_validator",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "jobs", "chain_validator.py")
    )
    obs_chain_validator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obs_chain_validator)
    validate_chain = obs_chain_validator.validate_chain

# Try importing verify_jwt from aeos_shared, otherwise fallback to simple jwt decode
try:
    from aeos_shared.auth import verify_jwt
except ImportError:
    from jose import jwt as jose_jwt
    def verify_jwt(token: str) -> dict:
        secret = os.environ.get("AEOS_JWT_SECRET", "test-secret-key-for-testing")
        return jose_jwt.decode(token, secret, algorithms=["HS256"])

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("observability-service")

app = FastAPI(title="Observability Service", version="1.0.0")

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/aeos")
MEMORY_AGENT_URL = os.environ.get("MEMORY_AGENT_URL", "http://localhost:8017")

# ---------------------------------------------------------------------------
# Socket.IO Setup
# ---------------------------------------------------------------------------
sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins="*")
# Removed duplicate ASGIApp instantiation

@sio.event
async def connect(sid, environ, auth=None):
    """Enforce JWT authentication on connection handshake."""
    query_str = environ.get("QUERY_STRING", "")
    query = parse_qs(query_str)
    token_list = query.get("token")
    
    if not token_list:
        logger.error(f"Connection rejected for SID {sid}: missing token query parameter.")
        raise ConnectionRefusedError("Missing authentication token")
        
    token = token_list[0]
    try:
        payload = verify_jwt(token)
        if hasattr(payload, "model_dump"):
            payload_dict = payload.model_dump()
        elif hasattr(payload, "dict"):
            payload_dict = payload.dict()
        else:
            payload_dict = payload
        await sio.save_session(sid, {"user": payload_dict})
        logger.info(f"Client {sid} connected successfully (User: {payload_dict.get('sub')}).")
    except Exception as e:
        logger.error(f"Connection rejected for SID {sid}: Invalid token: {e}")
        raise ConnectionRefusedError("Invalid authentication token")

@sio.on("subscribe")
async def handle_subscribe(sid, data):
    """Subscribe to a workflow's events and replay missed ones."""
    if not data or not isinstance(data, dict):
        return {"error": "Invalid subscribe data"}
        
    workflow_id = data.get("workflow_id")
    last_sequence = data.get("last_sequence", 0)
    
    if not workflow_id:
        return {"error": "Missing workflow_id"}
        
    await sio.enter_room(sid, workflow_id)
    logger.info(f"Client {sid} subscribed to workflow room {workflow_id}")
    
    # Replay buffered events from Redis
    try:
        r_client = redis.from_url(REDIS_URL, decode_responses=True)
        buffer_key = f"observability:buffer:{workflow_id}"
        
        # ZRANGEBYSCORE to get all events with sequence > last_sequence
        raw_events = await r_client.zrangebyscore(buffer_key, min=last_sequence + 1, max="+inf")
        await r_client.close()
        
        replayed_count = 0
        for raw_event in raw_events:
            event = json.loads(raw_event)
            await sio.emit("event", event, room=sid)
            replayed_count += 1
            
        logger.info(f"Replayed {replayed_count} events to client {sid} for workflow {workflow_id}")
        return {"status": "subscribed", "replayed": replayed_count}
    except Exception as e:
        logger.error(f"Failed to replay events for {workflow_id}: {e}")
        return {"error": f"Replay failed: {str(e)}"}

@sio.event
async def disconnect(sid):
    logger.info(f"Client {sid} disconnected.")

# The socket app will be combined with the FastAPI app at the bottom of the file

# ---------------------------------------------------------------------------
# REST Endpoints
# ---------------------------------------------------------------------------

@app.post("/observability/events")
async def ingest_event(event: dict):
    """Ingest a runtime event, persist to audit trail, buffer in Redis, and broadcast."""
    # Some agents emit flat events, while the coordinator nests them under 'payload'
    payload = event.get("payload", event)
    workflow_id = payload.get("workflow_id")
    event_type = event.get("type") or event.get("event_type", "unknown")
    
    # 1. Persist to audit trail via Memory Agent
    if event_type != "agent.state_changed":
        try:
            async with httpx.AsyncClient() as client:
                audit_resp = await client.post(
                    f"{MEMORY_AGENT_URL}/memory/audit",
                    json={
                        "event_type": event_type,
                        "agent_identity": payload.get("agent_identity", "observability"),
                        "incident_id": payload.get("incident_id"),
                        "workflow_id": workflow_id,
                        "action_description": payload.get("action_description") or f"Event {event_type} received",
                        "inputs": payload.get("inputs"),
                        "outputs": payload.get("outputs"),
                        "risk_score": payload.get("risk_score")
                    },
                    timeout=5.0
                )
                audit_data = audit_resp.json()
                # Attach prev_entry_hash to the event representation
                event["prev_entry_hash"] = audit_data.get("prev_entry_hash")
        except Exception as e:
            logger.error(f"Failed to persist event to audit trail: {e}")
            # Continue so we don't break real-time streaming, but log the failure
    
    # 1.5. Persist agent state in Redis
    if event_type == "agent.state_changed":
        try:
            r_client = redis.from_url(REDIS_URL, decode_responses=True)
            agent_role = payload.get("agent_role") or payload.get("agent")
            if agent_role:
                agent_state = {
                    "status": payload.get("status", "idle"),
                    "active_steps": payload.get("active_steps", 0),
                    "last_active": event.get("emitted_at") or event.get("timestamp") or datetime.utcnow().isoformat()
                }
                await r_client.hset("observability:agents", agent_role.lower(), json.dumps(agent_state))
                logger.info(f"Persisted state for agent {agent_role}: {agent_state}")
            await r_client.close()
        except Exception as e:
            logger.error(f"Failed to persist agent state in Redis: {e}")

    # 2. Buffer in Redis
    if workflow_id:
        try:
            r_client = redis.from_url(REDIS_URL, decode_responses=True)
            seq_key = f"observability:seq:{workflow_id}"
            buffer_key = f"observability:buffer:{workflow_id}"
            
            sequence = await r_client.incr(seq_key)
            event["sequence"] = sequence
            
            # Save to sorted set
            await r_client.zadd(buffer_key, {json.dumps(event): sequence})
            # Limit buffer to last 1000 items
            await r_client.zremrangebyrank(buffer_key, 0, -1001)
            # Set 24 hour expiry
            await r_client.expire(seq_key, 86400)
            await r_client.expire(buffer_key, 86400)
            
            await r_client.close()
        except Exception as e:
            logger.error(f"Failed to buffer event in Redis: {e}")
            
    # 3. Broadcast to Socket.IO room with SLA check
    start_time = time.perf_counter()
    if workflow_id:
        await sio.emit("event", event, room=workflow_id)
    
    # Always broadcast globally so global monitoring grids (Dashboard, Agents Page) get updates in real-time
    await sio.emit("event", event)
        
    duration = time.perf_counter() - start_time
    if duration > 1.0:
        logger.warning(f"SLA Breach: Broadcast latency of {duration:.3f}s exceeded 1.0s limit!")
        
    return {"status": "processed", "sequence": event.get("sequence")}

@app.get("/observability/traces/{workflow_id}")
async def get_workflow_trace(workflow_id: str):
    """Retrieve full execution trace and verify completeness."""
    trace = await build_execution_trace(workflow_id, DATABASE_URL)
    if "error" in trace:
        raise HTTPException(status_code=404, detail=trace["error"])
    return trace

@app.get("/observability/audit")
async def query_observability_audit(
    incident_id: Optional[str] = None,
    workflow_id: Optional[str] = None,
    agent: Optional[str] = None,
    event_type: Optional[str] = None,
    from_time: Optional[str] = Query(None, alias="from"),
    to_time: Optional[str] = Query(None, alias="to"),
    limit: int = 100,
    offset: int = 0
):
    """Forward audit query to Memory Agent with a 3-second response SLA."""
    start_time = time.perf_counter()
    try:
        params = {
            "incident_id": incident_id,
            "workflow_id": workflow_id,
            "agent": agent,
            "event_type": event_type,
            "from": from_time,
            "to": to_time,
            "limit": limit,
            "offset": offset
        }
        # filter out None values
        params = {k: v for k, v in params.items() if v is not None}
        
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{MEMORY_AGENT_URL}/memory/audit", params=params, timeout=5.0)
            if resp.status_code != 200:
                raise HTTPException(status_code=resp.status_code, detail=resp.text)
            data = resp.json()
            
            duration = time.perf_counter() - start_time
            if duration > 3.0:
                logger.warning(f"SLA Breach: Audit query response latency of {duration:.3f}s exceeded 3.0s limit!")
            return data
    except Exception as e:
        logger.error(f"Failed to query memory agent audit: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/observability/audit/validate-chain")
async def trigger_chain_validation(from_id: Optional[int] = None, to_id: Optional[int] = None):
    """Trigger chain validation job on-demand."""
    result = await validate_chain(from_id, to_id, DATABASE_URL)
    return result

@app.get("/observability/agents")
async def get_agents_status():
    """Retrieve the persisted status of all agents from Redis."""
    try:
        r_client = redis.from_url(REDIS_URL, decode_responses=True)
        agents_data = await r_client.hgetall("observability:agents")
        await r_client.close()
        
        parsed_agents = {}
        for role, state_str in agents_data.items():
            try:
                parsed_agents[role] = json.loads(state_str)
            except Exception:
                pass
        return parsed_agents
    except Exception as e:
        logger.error(f"Failed to retrieve agent states: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health():
    return {"status": "healthy", "service": "observability"}

# Combine Socket.IO and FastAPI into a single ASGI application
app = socketio.ASGIApp(sio, other_asgi_app=app, socketio_path="/ws/events")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8040)
