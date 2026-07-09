from aeos_shared import get, post, put, delete
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
import asyncpg
from aeos_shared import add_security_middleware, sanitize_text

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("recovery-agent")

app = FastAPI(title="Recovery Agent", version="1.0.0")
add_security_middleware(app)

# Service URLs from Environment
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/aeos")
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
WORKFLOW_ENGINE_URL = os.environ.get("WORKFLOW_ENGINE_URL", "http://workflow-engine:8030")
PLANNER_URL = os.environ.get("PLANNER_URL", "http://planner-agent:8010")
ESCALATION_URL = os.environ.get("ESCALATION_URL", "http://escalation-agent:8016")
MEMORY_AGENT_URL = os.environ.get("MEMORY_AGENT_URL", "http://memory-agent:8017")

class NotifyFailureRequest(BaseModel):
    workflow_id: str
    step_id: str
    incident_id: str
    error: str

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def classify_failure(error: str) -> str:
    """Heuristically classify the failure as transient or permanent."""
    error = sanitize_text(error)
    err_lower = error.lower()
    
    # Permanent failure keywords (e.g. invalid schemas, authorization issues, missing resources)
    permanent_keywords = [
        "404", "403", "401", "422", "invalid", "valueerror", "syntax", 
        "permission", "denied", "not found", "forbidden", "unauthorized",
        "validationerror", "keyerror", "typeerror"
    ]
    # Transient failure keywords (e.g. connection losses, timeouts)
    transient_keywords = [
        "timeout", "conn", "refused", "503", "502", "504", "socket", 
        "network", "temporary", "retryable", "busy", "lock", "deadlock"
    ]
    
    for p in permanent_keywords:
        if p in err_lower:
            return "permanent"
            
    for t in transient_keywords:
        if t in err_lower:
            return "transient"
            
    # Default to permanent if uncertain
    return "permanent"

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
    """Log recovery action to the Memory Agent Audit Trail."""
    event_type = sanitize_text(event_type)
    agent_identity = sanitize_text(agent_identity)
    action_description = sanitize_text(action_description)
    try:
        if True:
            await post(
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
                }
            )
    except Exception as e:
        logger.error(f"Failed to log recovery event to audit trail: {e}")

# ---------------------------------------------------------------------------
# Background Recovery Worker Flow
# ---------------------------------------------------------------------------

async def run_recovery_background(workflow_id: str, step_id: str, incident_id: str, error: str, classification: str):
    # Emit active state for recovery agent
    try:
        if True:
            await post(
                f"http://observability-service:8040/observability/events",
                json={
                    "type": "agent.state_changed",
                    "payload": {
                        "agent_role": "recovery",
                        "status": "active",
                        "active_steps": 1,
                        "incident_id": incident_id,
                        "workflow_id": workflow_id
                    },
                    "emitted_at": datetime.now(timezone.utc).isoformat()
                },
                timeout=2.0
            )
    except Exception:
        pass

    try:
        # 1. Log classification event to Memory Agent Audit Trail
        await log_audit_event(
            event_type="failure_classification",
            agent_identity="recovery-agent",
            incident_id=incident_id,
            workflow_id=workflow_id,
            action_description=f"Classified failure for step {step_id}: {classification}. Error: {error}"
        )
        
        if classification == "transient":
            # Check current retry count from PG DB
            conn = await asyncpg.connect(DATABASE_URL)
            row = await conn.fetchrow(
                "SELECT retry_count, action, agent_type FROM workflow_steps WHERE id = $1",
                uuid.UUID(step_id)
            )
            
            if row:
                retry_count = row["retry_count"]
                if retry_count < 3:
                    # Exponential backoff delay strictly doubling: 1s, 2s, 4s
                    delay = 1.0 * (2 ** retry_count)
                    logger.info(f"Transient failure for step {step_id}. Retrying (attempt {retry_count + 1}) after {delay}s...")
                    
                    # Update database retry count first
                    await conn.execute(
                        "UPDATE workflow_steps SET retry_count = retry_count + 1, updated_at = NOW() WHERE id = $1",
                        uuid.UUID(step_id)
                    )
                    await conn.close()
                    
                    # Log retry step in Audit Trail
                    await log_audit_event(
                        event_type="recovery_retry_attempt",
                        agent_identity="recovery-agent",
                        incident_id=incident_id,
                        workflow_id=workflow_id,
                        action_description=f"Retrying step {step_id} (attempt {retry_count + 1}) after {delay}s delay."
                    )
                    
                    # Perform delay
                    await asyncio.sleep(delay)
                    
                    # Trigger step execute call to Workflow Engine
                    if True:
                        exec_payload = {
                            "task_id": str(uuid.uuid4()),
                            "workflow_id": workflow_id,
                            "step_id": step_id,
                            "incident_id": incident_id,
                            "action": json.loads(row["action"]),
                            "context": {},
                            "permissions": []
                        }
                        try:
                            # Setting a reasonable timeout
                            await post(
                                f"{WORKFLOW_ENGINE_URL}/workflow/execute-step", 
                                json=exec_payload,
                                timeout=10.0
                            )
                            logger.info(f"Re-execution triggered successfully for step {step_id}")
                        except Exception as exec_err:
                            logger.error(f"Failed to trigger step re-execution: {exec_err}")
                    return
                else:
                    await conn.close()
                    logger.info(f"Retry limit (3) exceeded for step {step_id}. Treating as permanent failure.")
                    # Let it fall through to the permanent failure path
            else:
                await conn.close()
                logger.error(f"Step {step_id} not found in database. Recovery aborted.")
                return
 
        # 2. Permanent failure path (or transient failure exceeding retries)
        logger.info(f"Initiating replanning flow for workflow {workflow_id} due to step {step_id} failure.")
        
        # Log recovery replan trigger
        await log_audit_event(
            event_type="recovery_replan_triggered",
            agent_identity="recovery-agent",
            incident_id=incident_id,
            workflow_id=workflow_id,
            action_description=f"Triggering automatic replanning for workflow {workflow_id} due to permanent step {step_id} failure."
        )
        
        # Call planner-agent /planner/replan
        replan_success = False
        if True:
            try:
                res = await post(
                    f"{PLANNER_URL}/planner/replan",
                    json={
                        "workflow_id": workflow_id,
                        "failed_step_id": step_id,
                        "error": error
                    },
                    timeout=10.0
                )
                if res.status_code == 200:
                    logger.info("Successfully triggered planner replan")
                    replan_success = True
                else:
                    logger.error(f"Planner replan request failed: {res.text}")
            except Exception as pe:
                logger.error(f"Failed to communicate with planner-agent: {pe}")
                
        if replan_success:
            return
            
        # 3. Replanning failed or could not remediate -> Escalate to Escalation Agent
        logger.warn(f"Replanning unsuccessful. Escalating incident {incident_id}...")
        
        await log_audit_event(
            event_type="recovery_escalated_to_operator",
            agent_identity="recovery-agent",
            incident_id=incident_id,
            workflow_id=workflow_id,
            action_description=f"Replanning unsuccessful. Escalating workflow {workflow_id} step {step_id} failure to operator."
        )
        
        if True:
            try:
                await post(
                    f"{ESCALATION_URL}/escalation/notify",
                    json={
                        "incident_id": incident_id,
                        "workflow_id": workflow_id,
                        "step_id": step_id,
                        "reason": f"Automatic recovery failed. Step {step_id} failed permanently: {error}"
                    },
                    timeout=10.0
                )
                logger.info(f"Escalation successfully sent for step {step_id}")
            except Exception as ee:
                logger.error(f"Failed to contact Escalation Agent: {ee}")
                
    except Exception as e:
        logger.error(f"Unexpected error in recovery background routine: {e}")
    finally:
        # Emit idle state for recovery agent
        try:
            if True:
                await post(
                    f"http://observability-service:8040/observability/events",
                    json={
                        "type": "agent.state_changed",
                        "payload": {
                            "agent_role": "recovery",
                            "status": "idle",
                            "active_steps": 0,
                            "incident_id": incident_id,
                            "workflow_id": workflow_id
                        },
                        "emitted_at": datetime.now(timezone.utc).isoformat()
                    },
                    timeout=2.0
                )
        except Exception:
            pass

# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------

@app.post("/recovery/notify-failure")
async def notify_failure(req: NotifyFailureRequest, background_tasks: BackgroundTasks):
    req.workflow_id = sanitize_text(req.workflow_id)
    req.step_id = sanitize_text(req.step_id)
    req.incident_id = sanitize_text(req.incident_id)
    req.error = sanitize_text(req.error)
    logger.info(f"Received failure notification for step {req.step_id} in workflow {req.workflow_id}")
    
    # Classify failure quickly (enforces the 5-second response latency SLA limit)
    start_time = asyncio.get_event_loop().time()
    classification = classify_failure(req.error)
    
    # Run the backoff, retries, or replanning asynchronously in a background task
    background_tasks.add_task(
        run_recovery_background,
        req.workflow_id,
        req.step_id,
        req.incident_id,
        req.error,
        classification
    )
    
    duration = asyncio.get_event_loop().time() - start_time
    if duration > 5.0:
        logger.warning(f"SLA Warning: Failure classification took {duration}s (limit: 5s)")
        
    return {
        "status": "processing",
        "classification": classification,
        "action": "exponential_backoff" if classification == "transient" else "replan"
    }

@app.get("/health")
async def health():
    return {"status": "healthy", "service": "recovery"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8015)
