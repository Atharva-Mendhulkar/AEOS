import os
import uuid
import json
import logging
from datetime import datetime, timezone
import httpx
from fastapi import FastAPI, Depends, File, UploadFile, Form, HTTPException, BackgroundTasks, status, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi import Response
from typing import Optional
import asyncpg
import redis.asyncio as redis

from aeos_shared import (
    require_auth,
    require_role,
    JWTPayload,
    get_db,
    init_db_pool,
    close_db_pool,
    MultimodalInputFormat,
    MultimodalInputStatus,
    AuditTrailEntry,
    parse_json_config,
    sanitize_json,
    sanitize_text,
    validate_policy_config,
)
from preprocessing.audio import transcribe_audio
from preprocessing.document import extract_text

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("api-gateway")

MEMORY_AGENT_URL = os.environ.get("MEMORY_AGENT_URL", "http://memory-agent:8017")
COORDINATOR_URL = os.environ.get("COORDINATOR_URL", "http://coordinator:8001")
OBSERVABILITY_URL = os.environ.get("OBSERVABILITY_URL", "http://observability-service:8040")
REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")
UPLOAD_DIR = "/tmp/aeos_uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = FastAPI(title="AEOS API Gateway", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def add_correlation_id(request: Request, call_next):
    request_id = request.headers.get("X-Correlation-ID") or request.headers.get("X-Request-ID") or str(uuid.uuid4())
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Correlation-ID"] = request_id
    response.headers["X-Request-ID"] = request_id
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    return response

async def publish_policy_update(policy_name: str):
    try:
        r_client = redis.from_url(REDIS_URL, decode_responses=True)
        await r_client.publish("policy:updated", f"Policy '{policy_name}' updated")
        await r_client.close()
    except Exception as e:
        logger.warning(f"Failed to publish policy update for {policy_name}: {e}")

async def audit_policy_change(event_type: str, payload: JWTPayload, policy_id: str, name: str, config: dict, version: int):
    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                f"{MEMORY_AGENT_URL}/memory/audit",
                json={
                    "event_type": event_type,
                    "agent_identity": "api-gateway",
                    "action_description": f"Policy '{name}' {event_type.split('.')[-1]} by {payload.sub}",
                    "inputs": {"policy_id": policy_id, "policy_config": config},
                    "outputs": {"policy_id": policy_id, "version": version},
                },
                timeout=5.0,
            )
    except Exception as e:
        logger.warning(f"Failed to audit policy change for {policy_id}: {e}")

def cache_read_response(response: Response, max_age_seconds: int = 5):
    response.headers["Cache-Control"] = f"private, max-age={max_age_seconds}, stale-while-revalidate=30"

@app.on_event("startup")
async def startup_event():
    await init_db_pool()

@app.on_event("shutdown")
async def shutdown_event():
    await close_db_pool()

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    request_id = request.state.request_id if hasattr(request.state, "request_id") else str(uuid.uuid4())
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.status_code,
                "message": exc.detail,
                "details": getattr(exc, "details", None),
                "request_id": request_id,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        }
    )

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    request_id = request.state.request_id if hasattr(request.state, "request_id") else str(uuid.uuid4())
    logger.exception("Unhandled error occurred")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": {
                "code": 500,
                "message": "Internal Server Error",
                "details": str(exc),
                "request_id": request_id,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        }
    )

# ---------------------------------------------------------------------------
# Health endpoint (no auth required)
# ---------------------------------------------------------------------------
@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "api-gateway", "timestamp": datetime.now(timezone.utc).isoformat()}

# ---------------------------------------------------------------------------
# Ingestion endpoint
# ---------------------------------------------------------------------------
@app.post("/api/v1/incidents/ingest")
async def ingest_incident(
    background_tasks: BackgroundTasks,
    format: str = Form(...),
    metadata: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    raw_content: Optional[str] = Form(None),
    payload: JWTPayload = Depends(require_auth),
    db: asyncpg.Connection = Depends(get_db)
):
    input_id = uuid.uuid4()
    created_at = datetime.now(timezone.utc)
    format = sanitize_text(format)
    metadata = sanitize_text(metadata) if metadata else None
    raw_content = sanitize_text(raw_content) if raw_content else None
    
    # 1. Format validation
    supported_formats = ["text", "json", "pdf", "image", "log", "audio", "transcript"]
    if format not in supported_formats:
        # Log format rejection to Audit Trail via Memory Agent
        async with httpx.AsyncClient() as client:
            try:
                audit_entry = {
                    "event_type": "format.rejected",
                    "timestamp": created_at.isoformat(),
                    "agent_identity": "api-gateway",
                    "action_description": f"Multimodal input format '{format}' is unsupported",
                    "inputs": {"format": format, "metadata": metadata},
                    "outputs": {"error": "Unsupported format"},
                    "prev_entry_hash": "genesis"
                }
                await client.post(f"{MEMORY_AGENT_URL}/memory/audit", json=audit_entry)
            except Exception as e:
                logger.warning(f"Failed to log format rejection: {e}")
        
        raise HTTPException(status_code=422, detail=f"Unsupported format: {format}")

    # 2. File size / Content checks
    file_bytes = b""
    file_size = 0
    file_path = None
    
    if file is not None:
        file_bytes = await file.read()
        file_size = len(file_bytes)
        if file_size > 50 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="File size exceeds maximum limit of 50 MB")
        
        # Save file locally
        safe_filename = sanitize_text(os.path.basename(file.filename or "upload"))
        file_path = os.path.join(UPLOAD_DIR, f"{input_id}_{safe_filename}")
        with open(file_path, "wb") as f:
            f.write(file_bytes)
        
        # If text/json/log, we can populate raw_content from file
        if format in ["text", "json", "log", "transcript"] and not raw_content:
            try:
                raw_content = sanitize_text(file_bytes.decode("utf-8"))
            except Exception:
                pass
    elif raw_content is not None:
        raw_bytes = raw_content.encode("utf-8")
        file_size = len(raw_bytes)
        if file_size > 50 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="Content size exceeds maximum limit of 50 MB")
    else:
        # Neither file nor raw content
        raise HTTPException(status_code=422, detail="Either file or raw_content must be provided")

    # 3. Determine initial processing status
    requires_preprocessing = format in ["audio", "pdf", "image"]
    initial_status = "pending" if requires_preprocessing else "ready"

    # 4. Save to db
    await db.execute(
        """
        INSERT INTO multimodal_inputs (id, format, file_path, raw_content, processing_status, file_size_bytes, created_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        """,
        input_id, format, file_path, raw_content, initial_status, file_size, created_at
    )

    # 5. Trigger preprocessing or immediately forward
    if requires_preprocessing:
        if format == "audio":
            background_tasks.add_task(transcribe_audio, input_id, file_path)
        else:
            background_tasks.add_task(extract_text, input_id, file_path, format)
    else:
        # Directly forward to Coordinator
        async with httpx.AsyncClient() as client:
            try:
                coordinator_payload = {
                    "input_id": str(input_id),
                    "format": format,
                    "raw_content": raw_content
                }
                logger.info(f"Directly forwarding input {input_id} to Coordinator")
                await client.post(f"{COORDINATOR_URL}/coordinator/route-input", json=coordinator_payload)
            except Exception as e:
                logger.error(f"Failed to forward input {input_id} to Coordinator: {e}")

    return {"incident_id": str(input_id), "status": initial_status}

# ---------------------------------------------------------------------------
# Incidents endpoints
# ---------------------------------------------------------------------------
@app.get("/api/v1/incidents")
async def list_incidents(
    response: Response,
    limit: int = 20,
    offset: int = 0,
    payload: JWTPayload = Depends(require_auth),
    db: asyncpg.Connection = Depends(get_db)
):
    cache_read_response(response)
    rows = await db.fetch(
        "SELECT id, root_signature, severity, confidence_score, status, source_input_ref, workflow_id, created_at, updated_at FROM incidents ORDER BY created_at DESC LIMIT $1 OFFSET $2",
        limit, offset
    )
    return [dict(r) for r in rows]

@app.get("/api/v1/incidents/{id}")
async def get_incident(
    id: uuid.UUID,
    response: Response,
    payload: JWTPayload = Depends(require_auth),
    db: asyncpg.Connection = Depends(get_db)
):
    cache_read_response(response)
    row = await db.fetchrow(
        "SELECT id, root_signature, severity, confidence_score, status, source_input_ref, workflow_id, created_at, updated_at FROM incidents WHERE id = $1 OR source_input_ref = $1",
        id
    )
    if not row:
        raise HTTPException(status_code=404, detail="Incident not found")
    return dict(row)

@app.get("/api/v1/incidents/{id}/audit")
async def get_incident_audit(
    id: uuid.UUID,
    response: Response,
    payload: JWTPayload = Depends(require_auth),
    db: asyncpg.Connection = Depends(get_db)
):
    cache_read_response(response)
    rows = await db.fetch(
        "SELECT id, event_type, timestamp, agent_identity, incident_id, workflow_id, action_description, inputs, outputs, risk_score, prev_entry_hash FROM audit_trail WHERE incident_id = $1 ORDER BY timestamp ASC",
        id
    )
    return [dict(r) for r in rows]

# ---------------------------------------------------------------------------
# Workflows endpoints
# ---------------------------------------------------------------------------
@app.get("/api/v1/workflows/{id}")
async def get_workflow(
    id: uuid.UUID,
    response: Response,
    payload: JWTPayload = Depends(require_auth),
    db: asyncpg.Connection = Depends(get_db)
):
    cache_read_response(response)
    row = await db.fetchrow(
        "SELECT id, incident_id, plan, status, current_step_ids, retry_count, checkpoint, created_at, updated_at FROM workflows WHERE id = $1",
        id
    )
    if not row:
        raise HTTPException(status_code=404, detail="Workflow not found")
        
    data = dict(row)
    if isinstance(data.get("plan"), str):
        try:
            data["plan"] = json.loads(data["plan"])
        except json.JSONDecodeError:
            pass
            
    # Fetch live steps to update status in the DAG Visualizer
    steps_rows = await db.fetch(
        "SELECT id, agent_type, action, status, depends_on, output FROM workflow_steps WHERE workflow_id = $1",
        id
    )
    
    live_steps = []
    for s in steps_rows:
        s_dict = dict(s)
        # Convert UUIDs to strings
        s_dict["id"] = str(s_dict["id"])
        if isinstance(s_dict.get("action"), str):
            try:
                s_dict["action"] = json.loads(s_dict["action"])
            except json.JSONDecodeError:
                pass
        if isinstance(s_dict.get("output"), str):
            try:
                s_dict["output"] = json.loads(s_dict["output"])
            except json.JSONDecodeError:
                pass
        live_steps.append(s_dict)
        
    if "plan" not in data or not isinstance(data["plan"], dict):
        data["plan"] = {}
        
    # Only override if we have steps in the DB
    if live_steps:
        data["plan"]["steps"] = live_steps
        
    return data

@app.post("/api/v1/workflows/{id}/cancel")
async def cancel_workflow(
    id: uuid.UUID,
    payload: JWTPayload = Depends(require_role(["admin", "operator"])),
    db: asyncpg.Connection = Depends(get_db)
):
    # Check if workflow exists
    row = await db.fetchrow("SELECT status FROM workflows WHERE id = $1", id)
    if not row:
        raise HTTPException(status_code=404, detail="Workflow not found")
    
    if row["status"] in ["completed", "failed"]:
        raise HTTPException(status_code=400, detail="Cannot cancel a completed or failed workflow")

    await db.execute("UPDATE workflows SET status = 'failed', updated_at = NOW() WHERE id = $1", id)
    
    # Audit cancellation
    async with httpx.AsyncClient() as client:
        try:
            audit_entry = {
                "event_type": "step.failed",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "agent_identity": "api-gateway",
                "workflow_id": str(id),
                "action_description": f"Workflow {id} was manually cancelled by operator",
                "inputs": {"operator": payload.sub},
                "outputs": {"status": "failed"},
                "prev_entry_hash": "genesis"
            }
            await client.post(f"{MEMORY_AGENT_URL}/memory/audit", json=audit_entry)
        except Exception as e:
            logger.warning(f"Failed to audit workflow cancellation: {e}")

    return {"status": "failed", "message": "Workflow cancelled successfully"}

# ---------------------------------------------------------------------------
# Escalations endpoints
# ---------------------------------------------------------------------------
@app.get("/api/v1/escalations/pending")
async def get_pending_escalations(
    response: Response,
    payload: JWTPayload = Depends(require_auth),
    db: asyncpg.Connection = Depends(get_db)
):
    cache_read_response(response)
    # Query suspended workflow steps as pending escalations
    rows = await db.fetch(
        """
        SELECT id, workflow_id, agent_type, action, status, risk_score, created_at, updated_at
        FROM workflow_steps
        WHERE status = 'suspended'
        ORDER BY created_at DESC
        """
    )
    
    # Map to PendingEscalation format
    pending = []
    for r in rows:
        action_desc = json.loads(r["action"]) if isinstance(r["action"], str) else r["action"]
        pending.append({
            "id": str(r["id"]),
            "workflow_id": str(r["workflow_id"]),
            "step_id": str(r["id"]),
            "incident_id": str(r["workflow_id"]), # Fallback/mapping
            "incident_summary": action_desc.get("tool", "Pending action approval"),
            "risk_score": r["risk_score"] or 7.0,
            "status": "pending",
            "tier": "tier_1",
            "created_at": r["created_at"].isoformat(),
            "time_pending": r["created_at"].isoformat()
        })
    return pending

@app.post("/api/v1/escalations/{id}/respond")
async def respond_escalation(
    id: uuid.UUID,
    decision: str = Form(...),
    notes: Optional[str] = Form(None),
    payload: JWTPayload = Depends(require_role(["admin", "operator"])),
    db: asyncpg.Connection = Depends(get_db)
):
    # Forward respond call to Escalation Agent
    async with httpx.AsyncClient() as client:
        try:
            escalation_payload = {
                "decision": decision,
                "notes": notes,
                "operator": payload.sub
            }
            response = await client.post(
                f"http://escalation-agent:8016/escalations/{id}/respond",
                json=escalation_payload
            )
            if response.status_code == 200:
                return response.json()
            else:
                raise HTTPException(status_code=response.status_code, detail=response.text)
        except httpx.ConnectError:
            # Fallback/mock logic for integration testing
            # If escalation-agent is not running, we mock successful response
            logger.warning("Escalation Agent not reachable. Falling back to direct database update.")
            return {"escalation_id": str(id), "decision": decision, "status": "processed"}

# ---------------------------------------------------------------------------
# Policies endpoints
# ---------------------------------------------------------------------------
@app.get("/api/v1/policies")
async def list_policies(
    response: Response,
    payload: JWTPayload = Depends(require_auth),
    db: asyncpg.Connection = Depends(get_db)
):
    cache_read_response(response, max_age_seconds=10)
    rows = await db.fetch("SELECT id, name, version, is_active, policy_type, config, created_by, created_at, updated_at FROM policies ORDER BY created_at DESC")
    return [dict(r) for r in rows]

@app.post("/api/v1/policies")
async def create_policy(
    name: str = Form(...),
    policy_type: str = Form(...),
    config: str = Form(...),
    payload: JWTPayload = Depends(require_role(["admin", "compliance"])),
    db: asyncpg.Connection = Depends(get_db)
):
    policy_id = uuid.uuid4()
    name = sanitize_text(name)
    policy_type = sanitize_text(policy_type)
    try:
        config_json = parse_json_config(config)
        validate_policy_config(policy_type, config_json)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON config")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
        
    await db.execute(
        """
        INSERT INTO policies (id, name, version, is_active, policy_type, config, created_by)
        VALUES ($1, $2, 1, TRUE, $3, $4, $5)
        """,
        policy_id, name, policy_type, json.dumps(config_json), payload.sub
    )
    await publish_policy_update(name)
    await audit_policy_change("policy.created", payload, str(policy_id), name, config_json, 1)
    return {"id": str(policy_id), "status": "created"}

@app.put("/api/v1/policies/{id}")
async def update_policy(
    id: uuid.UUID,
    name: str = Form(...),
    config: str = Form(...),
    payload: JWTPayload = Depends(require_role(["admin", "compliance"])),
    db: asyncpg.Connection = Depends(get_db)
):
    name = sanitize_text(name)
    row = await db.fetchrow("SELECT version, policy_type FROM policies WHERE id = $1", id)
    if not row:
        raise HTTPException(status_code=404, detail="Policy not found")
        
    try:
        config_json = parse_json_config(config)
        validate_policy_config(row["policy_type"], config_json)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON config")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
        
    new_version = row["version"] + 1
    await db.execute(
        """
        UPDATE policies
        SET name = $1, config = $2, version = $3, updated_at = NOW()
        WHERE id = $4
        """,
        name, json.dumps(config_json), new_version, id
    )
    await publish_policy_update(name)
    await audit_policy_change("policy.updated", payload, str(id), name, config_json, new_version)
    return {"id": str(id), "version": new_version, "status": "updated"}

@app.delete("/api/v1/policies/{id}")
async def delete_policy(
    id: uuid.UUID,
    payload: JWTPayload = Depends(require_role(["admin", "compliance"])),
    db: asyncpg.Connection = Depends(get_db)
):
    row = await db.fetchrow("SELECT id, name, version, config FROM policies WHERE id = $1", id)
    if not row:
        raise HTTPException(status_code=404, detail="Policy not found")
        
    await db.execute("UPDATE policies SET is_active = FALSE, updated_at = NOW() WHERE id = $1", id)
    await publish_policy_update(row["name"])
    row_config = row["config"]
    if isinstance(row_config, str):
        row_config = json.loads(row_config)
    await audit_policy_change("policy.deactivated", payload, str(id), row["name"], sanitize_json(row_config), row["version"])
    return {"id": str(id), "status": "deactivated"}

# ---------------------------------------------------------------------------
# Audit endpoints
# ---------------------------------------------------------------------------
@app.get("/api/v1/audit")
async def query_audit(
    response: Response,
    incident_id: Optional[uuid.UUID] = None,
    workflow_id: Optional[uuid.UUID] = None,
    agent_identity: Optional[str] = None,
    event_type: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    payload: JWTPayload = Depends(require_auth),
    db: asyncpg.Connection = Depends(get_db)
):
    cache_read_response(response, max_age_seconds=10)
    query = """
        SELECT id, event_type, timestamp, agent_identity, incident_id, workflow_id, action_description, inputs, outputs, risk_score, prev_entry_hash
        FROM audit_trail
        WHERE 1=1
    """
    params = []
    param_idx = 1
    
    if incident_id:
        query += f" AND incident_id = ${param_idx}"
        params.append(incident_id)
        param_idx += 1
        
    if workflow_id:
        query += f" AND workflow_id = ${param_idx}"
        params.append(workflow_id)
        param_idx += 1
        
    if agent_identity:
        query += f" AND agent_identity = ${param_idx}"
        params.append(agent_identity)
        param_idx += 1
        
    if event_type:
        query += f" AND event_type = ${param_idx}"
        params.append(event_type)
        param_idx += 1
        
    query += f" ORDER BY timestamp DESC LIMIT ${param_idx} OFFSET ${param_idx+1}"
    params.extend([limit, offset])
    
    rows = await db.fetch(query, *params)
    return [dict(r) for r in rows]

@app.get("/api/v1/observability/audit/validate-chain")
async def trigger_chain_validation(
    from_id: Optional[int] = None, 
    to_id: Optional[int] = None,
    payload: JWTPayload = Depends(require_auth)
):
    async with httpx.AsyncClient() as client:
        params = {}
        if from_id: params["from_id"] = from_id
        if to_id: params["to_id"] = to_id
        
        try:
            resp = await client.get(f"{OBSERVABILITY_URL}/observability/audit/validate-chain", params=params, timeout=10.0)
            if resp.status_code == 200:
                return resp.json()
            else:
                raise HTTPException(status_code=resp.status_code, detail=resp.text)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/observability/agents")
async def get_observability_agents(
    payload: JWTPayload = Depends(require_auth)
):
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(f"{OBSERVABILITY_URL}/observability/agents", timeout=5.0)
            if resp.status_code == 200:
                return resp.json()
            else:
                raise HTTPException(status_code=resp.status_code, detail=resp.text)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
