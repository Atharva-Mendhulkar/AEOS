import os
import json
import uuid
import logging
import asyncio
from typing import Dict, Any, Optional
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
import httpx
import redis.asyncio as redis
import asyncpg

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("escalation-agent")

app = FastAPI(title="Escalation Agent", version="1.0.0")

# Service URLs from Environment
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/aeos")
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
WORKFLOW_ENGINE_URL = os.environ.get("WORKFLOW_ENGINE_URL", "http://workflow-engine:8030")
RECOVERY_AGENT_URL = os.environ.get("RECOVERY_AGENT_URL", "http://recovery-agent:8015")
OBSERVABILITY_URL = os.environ.get("OBSERVABILITY_URL", "http://observability-service:8040")
MEMORY_AGENT_URL = os.environ.get("MEMORY_AGENT_URL", "http://memory-agent:8017")

class NotifyRequest(BaseModel):
    incident_id: str
    workflow_id: str
    step_id: Optional[str] = None
    reason: str

class ResolveRequest(BaseModel):
    escalation_id: str
    approve: bool
    reason: Optional[str] = None

# Active escalations stored in-memory or Redis. We use Redis for robustness.
# We also run a background task for timeout monitoring.

@app.on_event("startup")
async def startup_event():
    # Start background timeout monitor task
    asyncio.create_task(monitor_escalation_timeouts())
    logger.info("Escalation Agent background timeout monitor started.")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def log_audit_event(
    event_type: str,
    agent_identity: str,
    incident_id: str,
    workflow_id: str,
    action_description: str,
    inputs: Optional[dict] = None,
    outputs: Optional[dict] = None,
    risk_score: Optional[float] = None
):
    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                f"{MEMORY_AGENT_URL}/memory/audit",
                json={
                    "event_type": event_type,
                    "agent_identity": agent_identity,
                    "incident_id": incident_id,
                    "workflow_id": workflow_id,
                    "action_description": action_description,
                    "inputs": inputs or {},
                    "outputs": outputs or {},
                    "risk_score": risk_score
                },
                timeout=5.0
            )
    except Exception as e:
        logger.error(f"Failed to write to audit trail: {e}")

# ---------------------------------------------------------------------------
# Background Timeout Monitoring Loop
# ---------------------------------------------------------------------------

async def check_escalation_timeouts():
    """Perform a single check of active escalations for operator timeout."""
    try:
        r_client = redis.from_url(REDIS_URL, decode_responses=True)
        active_keys = await r_client.keys("escalation:active:*")
        
        for key in active_keys:
            data_str = await r_client.get(key)
            if not data_str:
                continue
            
            esc = json.loads(data_str)
            if esc.get("status") != "pending":
                continue
            
            # Check timeout (e.g. 5 seconds for fast test recovery, or 30s)
            created_at = datetime.fromisoformat(esc["created_at"])
            elapsed = (datetime.now(timezone.utc) - created_at).total_seconds()
            
            # Default timeout: 3 seconds for tests to ensure fast feedback, customizable
            timeout_threshold = float(os.environ.get("ESCALATION_TIMEOUT_SEC", 3.0))
            
            tier = esc.get("tier", 1)
            
            if elapsed > timeout_threshold and tier == 1:
                # Escalate to Tier 2
                esc["tier"] = 2
                esc["created_at"] = datetime.now(timezone.utc).isoformat()
                await r_client.set(key, json.dumps(esc))
                
                logger.warn(f"Escalation {esc['escalation_id']} timed out on Tier 1. Escalating to Tier 2!")
                
                # Log audit and emit event
                await log_audit_event(
                    event_type="escalation_timeout",
                    agent_identity="escalation-agent",
                    incident_id=esc["incident_id"],
                    workflow_id=esc["workflow_id"],
                    action_description=f"Operator timeout on Tier 1. Escalating to Tier 2 for escalation {esc['escalation_id']}."
                )
                
                async with httpx.AsyncClient() as client:
                    try:
                        await client.post(
                            f"{OBSERVABILITY_URL}/observability/events",
                            json={
                                "type": "escalation.triggered",
                                "sequence": 1,
                                "payload": {
                                    "escalation_id": esc["escalation_id"],
                                    "incident_id": esc["incident_id"],
                                    "workflow_id": esc["workflow_id"],
                                    "step_id": esc["step_id"],
                                    "reason": esc["reason"],
                                    "tier": 2
                                },
                                "emitted_at": datetime.now(timezone.utc).isoformat()
                            }
                        )
                    except Exception as oe:
                        logger.error(f"Failed to emit Tier 2 escalation event: {oe}")
                        
        await r_client.close()
    except Exception as e:
        logger.error(f"Error in escalation timeout check: {e}")

async def monitor_escalation_timeouts():
    """Periodically check active escalations for operator timeout."""
    while True:
        try:
            await asyncio.sleep(1.0)
            await check_escalation_timeouts()
        except Exception as e:
            logger.error(f"Error in escalation timeout monitor: {e}")

# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------

@app.post("/escalation/notify")
async def notify(req: NotifyRequest):
    logger.info(f"Escalation notification triggered for workflow {req.workflow_id}")
    
    escalation_id = str(uuid.uuid4())
    
    # 1. Update PostgreSQL incident status to 'escalated'
    try:
        conn = await asyncpg.connect(DATABASE_URL)
        await conn.execute(
            "UPDATE incidents SET status = 'escalated', updated_at = NOW() WHERE id = $1",
            uuid.UUID(req.incident_id)
        )
        await conn.close()
    except Exception as e:
        logger.error(f"Failed to update incident status to escalated: {e}")
        # Continue anyway so system doesn't break
        
    # 2. Store escalation info in Redis
    esc_info = {
        "escalation_id": escalation_id,
        "incident_id": req.incident_id,
        "workflow_id": req.workflow_id,
        "step_id": req.step_id,
        "reason": req.reason,
        "status": "pending",
        "tier": 1,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    try:
        r_client = redis.from_url(REDIS_URL, decode_responses=True)
        await r_client.set(f"escalation:active:{escalation_id}", json.dumps(esc_info))
        await r_client.close()
    except Exception as re:
        logger.error(f"Failed to store escalation in Redis: {re}")
        
    # 3. Emit escalation.triggered WebSocket event to Observability Layer (SLA: < 30s)
    async with httpx.AsyncClient() as client:
        try:
            await client.post(
                f"{OBSERVABILITY_URL}/observability/events",
                json={
                    "type": "escalation.triggered",
                    "sequence": 1,
                    "payload": {
                        "escalation_id": escalation_id,
                        "incident_id": req.incident_id,
                        "workflow_id": req.workflow_id,
                        "step_id": req.step_id,
                        "reason": req.reason,
                        "tier": 1
                    },
                    "emitted_at": datetime.now(timezone.utc).isoformat()
                },
                timeout=5.0
            )
        except Exception as oe:
            logger.error(f"Failed to notify Observability Layer of escalation: {oe}")
            
    # 4. Log escalation trigger to Memory Agent Audit
    await log_audit_event(
        event_type="escalation_triggered",
        agent_identity="escalation-agent",
        incident_id=req.incident_id,
        workflow_id=req.workflow_id,
        action_description=f"Escalation {escalation_id} registered. Reason: {req.reason}"
    )
    
    return {
        "status": "notified",
        "escalation_id": escalation_id
    }

class RespondRequest(BaseModel):
    decision: str
    notes: Optional[str] = None
    operator: Optional[str] = None

@app.post("/escalations/{id}/respond")
async def respond_escalation_route(id: str, req: RespondRequest):
    logger.info(f"Operator {req.operator} responded to escalation {id} with decision {req.decision}")
    approve = req.decision in ["approve", "modify"]
    resolve_req = ResolveRequest(
        escalation_id=id,
        approve=approve,
        reason=req.notes or f"Decision {req.decision} made by operator {req.operator}"
    )
    return await resolve(resolve_req)

@app.post("/escalation/resolve")
async def resolve(req: ResolveRequest):
    logger.info(f"Resolving escalation {req.escalation_id}. Approved: {req.approve}")
    
    # 1. Fetch escalation info from Redis
    r_client = redis.from_url(REDIS_URL, decode_responses=True)
    esc_str = await r_client.get(f"escalation:active:{req.escalation_id}")
    if not esc_str:
        await r_client.close()
        raise HTTPException(status_code=404, detail="Escalation not found or already resolved")
        
    esc = json.loads(esc_str)
    esc["status"] = "resolved"
    
    # Delete from active list
    await r_client.delete(f"escalation:active:{req.escalation_id}")
    await r_client.close()
    
    workflow_id = esc["workflow_id"]
    step_id = esc["step_id"]
    incident_id = esc["incident_id"]
    
    # 2. Update PostgreSQL incident status back to 'in_progress'
    try:
        conn = await asyncpg.connect(DATABASE_URL)
        await conn.execute(
            "UPDATE incidents SET status = 'in_progress', updated_at = NOW() WHERE id = $1",
            uuid.UUID(incident_id)
        )
        await conn.close()
    except Exception as e:
        logger.error(f"Failed to reset incident status in Postgres: {e}")
        
    # 3. Route approval decision (SLA: < 5s)
    start_time = asyncio.get_event_loop().time()
    
    async with httpx.AsyncClient() as client:
        if req.approve:
            # Resuming step execution in workflow engine
            try:
                res = await client.post(
                    f"{WORKFLOW_ENGINE_URL}/workflow/resume-step",
                    json={
                        "workflow_id": workflow_id,
                        "step_id": step_id,
                        "approved": True,
                        "reason": req.reason or "Approved by operator"
                    },
                    timeout=5.0
                )
                logger.info(f"Resumed workflow step {step_id}: {res.status_code}")
            except Exception as we_err:
                logger.error(f"Failed to contact workflow-engine to resume step: {we_err}")
        else:
            # Reject: trigger recovery pipeline
            try:
                res = await client.post(
                    f"{RECOVERY_AGENT_URL}/recovery/notify-failure",
                    json={
                        "workflow_id": workflow_id,
                        "step_id": step_id,
                        "incident_id": incident_id,
                        "error": f"Operator approval rejected. Reason: {req.reason or 'No reason provided'}"
                    },
                    timeout=5.0
                )
                logger.info(f"Triggered recovery agent failure path: {res.status_code}")
            except Exception as rec_err:
                logger.error(f"Failed to call recovery-agent: {rec_err}")
                
    duration = asyncio.get_event_loop().time() - start_time
    if duration > 5.0:
        logger.warning(f"SLA Warning: Escalation resolution routing took {duration}s (limit: 5s)")
        
    # 4. Emit escalation.resolved event to Observability
    async with httpx.AsyncClient() as client:
        try:
            await client.post(
                f"{OBSERVABILITY_URL}/observability/events",
                json={
                    "type": "escalation.resolved",
                    "sequence": 2,
                    "payload": {
                        "escalation_id": req.escalation_id,
                        "workflow_id": workflow_id,
                        "step_id": step_id,
                        "approved": req.approve,
                        "reason": req.reason
                    },
                    "emitted_at": datetime.now(timezone.utc).isoformat()
                },
                timeout=5.0
            )
        except Exception as oe:
            logger.error(f"Failed to emit escalation.resolved event: {oe}")
            
    # 5. Log outcome to memory agent audit
    await log_audit_event(
        event_type="escalation_resolved",
        agent_identity="escalation-agent",
        incident_id=incident_id,
        workflow_id=workflow_id,
        action_description=f"Escalation {req.escalation_id} resolved. Approved: {req.approve}. Reason: {req.reason or ''}"
    )
    
    return {
        "status": "resolved",
        "escalation_id": req.escalation_id
    }

@app.get("/health")
async def health():
    return {"status": "healthy", "service": "escalation"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8016)
