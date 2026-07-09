from aeos_shared import create_graceful_lifespan
from prometheus_fastapi_instrumentator import Instrumentator
import os
import json
import uuid
import logging
import hashlib
import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Request, Response, status, Query
from pydantic import BaseModel, Field
import asyncpg
import redis.asyncio as redis
from aeos_shared import add_security_middleware, sanitize_json, sanitize_model_text_fields, sanitize_text
from memory_jobs.retention import enforce_retention

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("memory-agent")

app = FastAPI(title="Memory Agent", version="1.0.0")

# Expose Prometheus metrics
Instrumentator().instrument(app).expose(app)

add_security_middleware(app)

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/aeos")
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
MEMORY_CONTEXT_QUERY_TIMEOUT_MS = int(os.environ.get("MEMORY_CONTEXT_QUERY_TIMEOUT_MS", 500))
OBSERVABILITY_URL = os.environ.get("OBSERVABILITY_URL", "http://observability-service:8040")

db_pool = None
redis_client = None


async def startup():
    global db_pool, redis_client
    db_pool = await asyncpg.create_pool(DATABASE_URL)
    redis_client = redis.from_url(REDIS_URL, decode_responses=True)
    logger.info("Memory Agent started database pool and Redis connection.")


async def shutdown():
    if db_pool:
        await db_pool.close()
    if redis_client:
        await redis_client.close()
    logger.info("Memory Agent connection pool closed.")

# ---------------------------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------------------------

class WorkflowState(BaseModel):
    id: str
    incident_id: str
    plan: Optional[dict] = None
    status: str
    current_step_ids: Optional[List[str]] = Field(default_factory=list)
    checkpoint: Optional[dict] = None
    retry_count: int = 0

class PlanState(BaseModel):
    workflow_id: str
    plan: dict

class ContextQueryRequest(BaseModel):
    context_type: str
    query_text: Optional[str] = None
    filter: Optional[dict] = None
    limit: int = 10

class ContextRecord(BaseModel):
    context_type: str
    incident_id: Optional[str] = None
    agent_type: Optional[str] = None
    content: dict
    embedding_vector: Optional[List[float]] = None

class AuditEntry(BaseModel):
    event_type: str
    agent_identity: str
    incident_id: Optional[str] = None
    workflow_id: Optional[str] = None
    action_description: str
    inputs: Optional[dict] = None
    outputs: Optional[dict] = None
    risk_score: Optional[float] = None

# ---------------------------------------------------------------------------
# Helper functions for Canonical Hash Calculation
# ---------------------------------------------------------------------------

def make_canonical_dict(row: dict) -> dict:
    """Normalize fields to standard primitive types for deterministic serialization."""
    res = {}
    keys = [
        "event_type", "timestamp", "agent_identity", "incident_id", 
        "workflow_id", "action_description", "inputs", "outputs", 
        "risk_score", "prev_entry_hash"
    ]
    for k in keys:
        val = row.get(k)
        if val is None:
            res[k] = None
        elif isinstance(val, datetime):
            res[k] = val.astimezone(timezone.utc).isoformat()
        elif isinstance(val, uuid.UUID):
            res[k] = str(val)
        elif isinstance(val, (dict, list)):
            res[k] = json.loads(json.dumps(val, sort_keys=True))
        elif isinstance(val, str) and (val.startswith("{") or val.startswith("[")):
            try:
                res[k] = json.loads(val)
            except Exception:
                res[k] = val
        elif isinstance(val, float):
            res[k] = round(val, 4)
        else:
            res[k] = val
    return res

def compute_entry_hash(row: dict) -> str:
    canonical = make_canonical_dict(row)
    serialized = json.dumps(canonical, sort_keys=True)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

# ---------------------------------------------------------------------------
# REST Endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    return {"status": "healthy", "service": "memory"}

@app.post("/memory/workflows")
async def save_workflow(state: WorkflowState):
    """Upsert workflow state to PostgreSQL."""
    state = sanitize_model_text_fields(state)
    try:
        plan_json = json.dumps(sanitize_json(state.plan or {}))
        checkpoint_json = json.dumps(sanitize_json(state.checkpoint or {}))
        
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO workflows (id, incident_id, plan, status, current_step_ids, checkpoint, retry_count, updated_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, NOW())
                ON CONFLICT (id) DO UPDATE SET
                    incident_id = EXCLUDED.incident_id,
                    plan = EXCLUDED.plan,
                    status = EXCLUDED.status,
                    current_step_ids = EXCLUDED.current_step_ids,
                    checkpoint = EXCLUDED.checkpoint,
                    retry_count = EXCLUDED.retry_count,
                    updated_at = NOW()
                """,
                uuid.UUID(state.id),
                uuid.UUID(state.incident_id),
                plan_json,
                state.status,
                [uuid.UUID(sid) for sid in (state.current_step_ids or [])],
                checkpoint_json,
                state.retry_count
            )
        return {"status": "persisted", "workflow_id": state.id}
    except Exception as e:
        logger.error(f"Error persisting workflow {state.id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to persist workflow: {str(e)}")

@app.get("/memory/workflows")
async def get_workflows(status: Optional[str] = None):
    """Retrieve workflows, optionally filtered by comma-separated status values."""
    try:
        query = "SELECT id, incident_id, plan, status, current_step_ids, checkpoint, retry_count FROM workflows"
        params = []
        if status:
            status_list = [s.strip() for s in status.split(",")]
            query += " WHERE status = ANY($1)"
            params.append(status_list)
            
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
            
        results = []
        for r in rows:
            plan_data = r["plan"]
            if isinstance(plan_data, str):
                plan_data = json.loads(plan_data)
            checkpoint_data = r["checkpoint"]
            if isinstance(checkpoint_data, str):
                checkpoint_data = json.loads(checkpoint_data)
                
            results.append({
                "id": str(r["id"]),
                "incident_id": str(r["incident_id"]),
                "plan": plan_data,
                "status": r["status"],
                "current_step_ids": [str(sid) for sid in r["current_step_ids"]] if r["current_step_ids"] else [],
                "checkpoint": checkpoint_data,
                "retry_count": r["retry_count"]
            })
        return results
    except Exception as e:
        logger.error(f"Error retrieving workflows: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/memory/workflows/{workflow_id}/checkpoint")
async def get_checkpoint(workflow_id: str):
    """Retrieve checkpoint from workflows table."""
    try:
        wf_uuid = uuid.UUID(workflow_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid workflow ID format")

    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT checkpoint FROM workflows WHERE id = $1",
            wf_uuid
        )
        if not row:
            raise HTTPException(status_code=404, detail="Workflow not found")
        
        checkpoint_data = row["checkpoint"]
        if checkpoint_data is None:
            return {"checkpoint": {}}
        
        if isinstance(checkpoint_data, str):
            return {"checkpoint": json.loads(checkpoint_data)}
        return {"checkpoint": checkpoint_data}

@app.post("/memory/plans")
async def save_plan(state: PlanState):
    """Persist plan to workflows.plan."""
    state = sanitize_model_text_fields(state)
    try:
        wf_uuid = uuid.UUID(state.workflow_id)
        plan_json = json.dumps(sanitize_json(state.plan))
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid parameter format")

    async with db_pool.acquire() as conn:
        result = await conn.execute(
            "UPDATE workflows SET plan = $1, updated_at = NOW() WHERE id = $2",
            plan_json,
            wf_uuid
        )
        # If workflow doesn't exist, we return status update missing.
        # But coordinator usually inserts the workflow structure first.
        return {"status": "persisted", "workflow_id": state.workflow_id}

@app.post("/memory/context")
async def store_context(record: ContextRecord):
    """Store operational context record in PostgreSQL database."""
    record = sanitize_model_text_fields(record)
    try:
        inc_uuid = uuid.UUID(record.incident_id) if record.incident_id else None
        
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO operational_context (context_type, incident_id, agent_type, content, embedding_vector, created_at)
                VALUES ($1, $2, $3, $4, $5, NOW())
                """,
                record.context_type,
                inc_uuid,
                record.agent_type,
                json.dumps(sanitize_json(record.content)),
                record.embedding_vector
            )
        return {"status": "stored"}
    except Exception as e:
        logger.error(f"Error storing context: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/memory/context/query")
async def query_context(req: ContextQueryRequest):
    """Query operational context within the configured SLA timebudget."""
    req = sanitize_model_text_fields(req)
    timeout_seconds = MEMORY_CONTEXT_QUERY_TIMEOUT_MS / 1000.0
    
    async def perform_query():
        # Build SQL matching criteria
        conditions = ["context_type = $1"]
        params = [req.context_type]
        
        if req.query_text:
            params.append(f"%{req.query_text}%")
            conditions.append(f"content::text ILIKE ${len(params)}")
            
        if req.filter:
            params.append(json.dumps(sanitize_json(req.filter)))
            conditions.append(f"content @> ${len(params)}::jsonb")
            
        sql = f"""
            SELECT id, context_type, incident_id, agent_type, content, created_at
            FROM operational_context
            WHERE {" AND ".join(conditions)}
            ORDER BY created_at DESC
            LIMIT ${len(params) + 1}
        """
        params.append(req.limit)
        
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(sql, *params)
            
        results = []
        for r in rows:
            content_data = r["content"]
            if isinstance(content_data, str):
                content_data = json.loads(content_data)
            results.append({
                "id": str(r["id"]),
                "context_type": r["context_type"],
                "incident_id": str(r["incident_id"]) if r["incident_id"] else None,
                "agent_type": r["agent_type"],
                "content": content_data,
                "created_at": r["created_at"].isoformat()
            })
        return results

    try:
        return await asyncio.wait_for(perform_query(), timeout=timeout_seconds)
    except asyncio.TimeoutError:
        logger.error(f"SLA Breach: Context query took longer than {MEMORY_CONTEXT_QUERY_TIMEOUT_MS}ms")
        raise HTTPException(status_code=504, detail="Operational context search exceeded SLA limit")
    except Exception as e:
        logger.error(f"Error querying context: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

audit_lock = asyncio.Lock()

@app.post("/memory/audit")
async def append_audit(entry: AuditEntry):
    """Append a hash-chained, tamper-evident entry to the audit trail."""
    entry = sanitize_model_text_fields(entry)
    try:
        inc_uuid = uuid.UUID(entry.incident_id) if entry.incident_id else None
        wf_uuid = uuid.UUID(entry.workflow_id) if entry.workflow_id else None
        
        async with audit_lock:
            async with db_pool.acquire() as conn:
                # 1. Fetch latest entry to get its hash
                # Since audit_trail is partitioned, ORDER BY id DESC works or ordering by timestamp, id
                prev_row = await conn.fetchrow(
                    """
                    SELECT event_type, timestamp, agent_identity, incident_id, workflow_id, 
                           action_description, inputs, outputs, risk_score, prev_entry_hash
                    FROM audit_trail
                    ORDER BY id DESC LIMIT 1
                    """
                )
                
                if not prev_row:
                    prev_entry_hash = "genesis"
                else:
                    prev_entry_hash = compute_entry_hash(dict(prev_row))
                    
                # 2. Insert new entry with prev_entry_hash
                inputs_json = json.dumps(sanitize_json(entry.inputs or {}))
                outputs_json = json.dumps(sanitize_json(entry.outputs or {}))
                
                await conn.execute(
                    """
                    INSERT INTO audit_trail (
                        event_type, timestamp, agent_identity, incident_id, workflow_id,
                        action_description, inputs, outputs, risk_score, prev_entry_hash, created_at
                    ) VALUES ($1, NOW(), $2, $3, $4, $5, $6, $7, $8, $9, NOW())
                    """,
                    entry.event_type,
                    entry.agent_identity,
                    inc_uuid,
                    wf_uuid,
                    entry.action_description,
                    inputs_json,
                    outputs_json,
                    entry.risk_score,
                    prev_entry_hash
                )
        return {"status": "audited", "prev_entry_hash": prev_entry_hash}
    except Exception as e:
        logger.error(f"Failed to append to audit trail: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Audit write failed: {str(e)}")

@app.get("/memory/audit")
async def query_audit(
    incident_id: Optional[str] = None,
    workflow_id: Optional[str] = None,
    agent: Optional[str] = None,
    event_type: Optional[str] = None,
    from_time: Optional[str] = Query(None, alias="from"),
    to_time: Optional[str] = Query(None, alias="to"),
    limit: int = 100,
    offset: int = 0
):
    """Query audit trail with filters."""
    try:
        agent = sanitize_text(agent) if agent else None
        event_type = sanitize_text(event_type) if event_type else None
        conditions = ["1=1"]
        params = []
        
        if incident_id:
            params.append(uuid.UUID(incident_id))
            conditions.append(f"incident_id = ${len(params)}")
            
        if workflow_id:
            params.append(uuid.UUID(workflow_id))
            conditions.append(f"workflow_id = ${len(params)}")
            
        if agent:
            params.append(agent)
            conditions.append(f"agent_identity = ${len(params)}")
            
        if event_type:
            params.append(event_type)
            conditions.append(f"event_type = ${len(params)}")
            
        if from_time:
            # Parse from_time and convert to datetime if possible
            params.append(datetime.fromisoformat(from_time.replace("Z", "+00:00")))
            conditions.append(f"timestamp >= ${len(params)}")
            
        if to_time:
            params.append(datetime.fromisoformat(to_time.replace("Z", "+00:00")))
            conditions.append(f"timestamp <= ${len(params)}")
            
        sql = f"""
            SELECT id, event_type, timestamp, agent_identity, incident_id, workflow_id,
                   action_description, inputs, outputs, risk_score, prev_entry_hash, created_at
            FROM audit_trail
            WHERE {" AND ".join(conditions)}
            ORDER BY id DESC
            LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}
        """
        params.extend([limit, offset])
        
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(sql, *params)
            
        results = []
        for r in rows:
            inputs_data = r["inputs"]
            if isinstance(inputs_data, str):
                inputs_data = json.loads(inputs_data)
            outputs_data = r["outputs"]
            if isinstance(outputs_data, str):
                outputs_data = json.loads(outputs_data)
                
            results.append({
                "id": r["id"],
                "event_type": r["event_type"],
                "timestamp": r["timestamp"].isoformat(),
                "agent_identity": r["agent_identity"],
                "incident_id": str(r["incident_id"]) if r["incident_id"] else None,
                "workflow_id": str(r["workflow_id"]) if r["workflow_id"] else None,
                "action_description": r["action_description"],
                "inputs": inputs_data,
                "outputs": outputs_data,
                "risk_score": r["risk_score"],
                "prev_entry_hash": r["prev_entry_hash"]
            })
        return results
    except Exception as e:
        logger.error(f"Error querying audit trail: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/memory/retention/enforce")
async def enforce_retention_endpoint(retention_days: int = Query(90, ge=1)):
    """Manually trigger retention enforcement for operational verification."""
    try:
        return await enforce_retention(DATABASE_URL, retention_days)
    except Exception as e:
        logger.error(f"Retention enforcement failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8017)


# Inject Graceful Lifespan
app.router.lifespan_context = create_graceful_lifespan(
    startup_func=startup,
    shutdown_func=shutdown
)
