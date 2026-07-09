from aeos_shared import get, post, put, delete
import os
import time
import logging
import httpx
import asyncio
import uuid
import json
from typing import Dict, Any, Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from celery import Celery
from aeos_shared import add_security_middleware, sanitize_json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("workflow-engine")

app = FastAPI(title="Workflow Engine", version="1.0.0")
add_security_middleware(app)

# URLs and environment configurations
REDIS_URL = os.environ.get("REDIS_URL", "redis://:aeosredis@redis:6379/0")
COORDINATOR_URL = os.environ.get("COORDINATOR_URL", "http://coordinator:8001")
GOVERNANCE_URL = os.environ.get("GOVERNANCE_URL", "http://governance-service:8020")
RECOVERY_AGENT_URL = os.environ.get("RECOVERY_AGENT_URL", "http://recovery-agent:8025")
ESCALATION_AGENT_URL = os.environ.get("ESCALATION_AGENT_URL", "http://escalation-agent:8015")
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@postgres:5432/aeos")

# Celery Setup
celery_app = Celery("workflow_tasks", broker=REDIS_URL, backend=REDIS_URL)
celery_app.conf.update(
    task_always_eager=os.environ.get("CELERY_ALWAYS_EAGER", "False").lower() in ("true", "1", "t"),
)

# ---------------------------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------------------------
class ActionDescriptor(BaseModel):
    tool: str
    params: dict = Field(default_factory=dict)
    timeout_seconds: int = 30

class ExecuteStepRequest(BaseModel):
    task_id: str
    workflow_id: str
    step_id: str
    incident_id: str
    action: ActionDescriptor
    context: dict = Field(default_factory=dict)
    permissions: list = Field(default_factory=list)

class ResumeStepRequest(BaseModel):
    workflow_id: str
    step_id: str
    approved: bool
    reason: Optional[str] = None

# ---------------------------------------------------------------------------
# Mock Tool Execution Logic
# ---------------------------------------------------------------------------
async def execute_tool_logic(tool: str, params: dict, timeout_seconds: int) -> dict:
    """Executes specific tools, supporting timeouts and simulated errors."""
    start_time = time.time()
    
    # Enforce tool delay simulation
    delay = params.get("delay_seconds", 0.1)
    
    # Timeout check
    if delay > timeout_seconds:
        await asyncio.sleep(timeout_seconds)
        raise asyncio.TimeoutError(f"Tool {tool} timed out after {timeout_seconds}s")
        
    await asyncio.sleep(delay)
    
    if params.get("fail", False):
        raise ValueError(f"Simulated failure execution of tool {tool}")

    # Tool specific mock responses
    if tool == "restart_service":
        return {"status": "success", "service": params.get("service_name", "unknown"), "restarted_at": datetime_now_iso()}
    elif tool == "gather_logs":
        return {"status": "success", "service": params.get("service", "unknown"), "log_lines": 50, "logs": "Logs matched: No anomalies."}
    elif tool == "verify_policy":
        return {"status": "success", "policy_id": params.get("policy_id", "default"), "compliance": "verified"}
    elif tool == "remediate_failure":
        return {"status": "success", "remedied": True}
    else:
        # Fallback generic tool execution
        return {"status": "success", "executed_tool": tool, "params": params}

def datetime_now_iso():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()

# ---------------------------------------------------------------------------
# Celery Execution Task
# ---------------------------------------------------------------------------
@celery_app.task(name="tasks.execute_step")
def celery_execute_step(task_data: dict):
    """Celery worker execution block (sync wrapper over async logic)."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        # Running inside an active event loop (e.g. FastAPI TestClient)
        # Execute coroutine in a separate thread to block synchronously and wait
        import threading
        result = []
        error = []

        def target():
            try:
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                val = new_loop.run_until_complete(async_celery_execute_step(task_data))
                result.append(val)
            except Exception as e:
                error.append(e)

        t = threading.Thread(target=target)
        t.start()
        t.join()
        if error:
            raise error[0]
        return result[0] if result else None
    else:
        # Standard Celery worker execution
        new_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(new_loop)
        return new_loop.run_until_complete(async_celery_execute_step(task_data))

async def async_celery_execute_step(task_data: dict):
    task_id = task_data["task_id"]
    workflow_id = task_data["workflow_id"]
    step_id = task_data["step_id"]
    incident_id = task_data["incident_id"]
    action = task_data["action"]
    
    tool = action["tool"]
    params = action["params"]
    timeout = action.get("timeout_seconds", 30)

    logger.info(f"Worker running step {step_id} ({tool}) for workflow {workflow_id}")

    try:
        # Execute tool
        output = await asyncio.wait_for(
            execute_tool_logic(tool, params, timeout),
            timeout=float(timeout)
        )
        
        # Report success back to Coordinator
        if True:
            await post(
                f"{COORDINATOR_URL}/coordinator/step-complete",
                json={
                    "task_id": task_id,
                    "step_id": step_id,
                    "workflow_id": workflow_id,
                    "incident_id": incident_id,
                    "output": output
                }
            )
        logger.info(f"Step {step_id} completed successfully.")
        
    except Exception as e:
        logger.error(f"Step {step_id} execution failed: {e}")
        error_msg = str(e)
        
        # Invoke Recovery Agent via POST /recovery/notify-failure
        recovery_triggered = False
        if True:
            try:
                rec_res = await post(
                    f"{RECOVERY_AGENT_URL}/recovery/notify-failure",
                    json={
                        "workflow_id": workflow_id,
                        "step_id": step_id,
                        "incident_id": incident_id,
                        "error": error_msg
                    }
                )
                if rec_res.status_code == 200:
                    recovery_triggered = True
                    logger.info(f"Recovery Agent successfully notified for step {step_id}")
            except Exception as rec_err:
                logger.error(f"Failed to call Recovery Agent: {rec_err}")

        # If Recovery Agent was not triggered or returns direct failure, notify Coordinator of failure
        if not recovery_triggered:
            if True:
                try:
                    await post(
                        f"{COORDINATOR_URL}/coordinator/step-failed",
                        json={
                            "task_id": task_id,
                            "step_id": step_id,
                            "workflow_id": workflow_id,
                            "incident_id": incident_id,
                            "error": error_msg
                        }
                    )
                except Exception as coord_err:
                    logger.error(f"Failed to report step failure to Coordinator: {coord_err}")

# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------
@app.post("/workflow/execute-step")
async def execute_step(req: ExecuteStepRequest):
    req.action.tool = sanitize_json(req.action.tool)
    req.action.params = sanitize_json(req.action.params)
    req.context = sanitize_json(req.context)
    logger.info(f"Received execution request for step {req.step_id} of workflow {req.workflow_id}")

    # 1. Call Governance validate-action
    risk_score = 5.0
    approved = True
    if True:
        try:
            gov_res = await post(
                f"{GOVERNANCE_URL}/governance/validate-action",
                json={
                    "action": req.action.model_dump(),
                    "agent_type": "operations" # default
                }
            )
            gov_data = gov_res.json()
            risk_score = gov_data.get("risk_score", 5.0)
            approved = gov_data.get("approved", True)
        except Exception as e:
            logger.warn(f"Failed to communicate with Governance Layer: {e}. Defaulting to low risk (5.0)")

    # 2. Gate checking based on risk score
    if not approved or risk_score >= 9.0:
        # Halt / Circuit Breaker
        logger.error(f"Step {req.step_id} halted by Governance (risk: {risk_score})")
        if True:
            try:
                await post(
                    f"{COORDINATOR_URL}/coordinator/step-failed",
                    json={
                        "task_id": req.task_id,
                        "step_id": req.step_id,
                        "workflow_id": req.workflow_id,
                        "incident_id": req.incident_id,
                        "error": f"Governance Circuit Breaker activated. Risk score: {risk_score}"
                    }
                )
            except Exception as ce:
                logger.error(f"Failed to report circuit breaker to Coordinator: {ce}")
        return {"status": "halted", "risk_score": risk_score}

    elif risk_score >= 7.0:
        # Suspend step / Approval Gate
        logger.warn(f"Step {req.step_id} suspended. Requires manual approval (risk: {risk_score})")
        
        # Suspend status update in DB via direct DB Pool connection or via a call.
        # Since we have DATABASE_URL, we can update it if needed.
        # But wait! The test or Coordinator will wait.
        # Let's make a request to Escalation Agent to notify approval is pending
        if True:
            try:
                await post(
                    f"{ESCALATION_AGENT_URL}/escalation/notify",
                    json={
                        "incident_id": req.incident_id,
                        "workflow_id": req.workflow_id,
                        "step_id": req.step_id,
                        "reason": f"Manual approval required for step {req.step_id} (risk score: {risk_score})"
                    }
                )
            except Exception as ee:
                logger.error(f"Failed to notify Escalation Agent: {ee}")

        # Update step status in DB to suspended
        import asyncpg
        try:
            conn = await asyncpg.connect(DATABASE_URL)
            await conn.execute(
                "UPDATE workflow_steps SET status = 'suspended', risk_score = $1, updated_at = NOW() WHERE id = $2",
                risk_score, uuid.UUID(req.step_id)
            )
            await conn.close()
        except Exception as dbe:
            logger.error(f"Failed to update step to suspended in PostgreSQL: {dbe}")

        return {"status": "suspended", "risk_score": risk_score}

    # 3. Approved: trigger Celery async task execution
    task_payload = req.model_dump()
    celery_execute_step.delay(task_payload)
    return {"status": "executing", "risk_score": risk_score}

@app.post("/workflow/resume-step")
async def resume_step(req: ResumeStepRequest):
    req.reason = sanitize_json(req.reason) if req.reason else None
    logger.info(f"Resuming step {req.step_id} for workflow {req.workflow_id}. Approved: {req.approved}")
    
    # Update step status from suspended back to active in DB
    import asyncpg
    try:
        conn = await asyncpg.connect(DATABASE_URL)
        step_row = await conn.fetchrow(
            "SELECT action, agent_type, workflow_id FROM workflow_steps WHERE id = $1",
            uuid.UUID(req.step_id)
        )
        if not step_row:
            raise HTTPException(status_code=404, detail="Step not found")
            
        incident_row = await conn.fetchrow(
            "SELECT incident_id FROM workflows WHERE id = $1",
            uuid.UUID(req.workflow_id)
        )
        incident_id = str(incident_row["incident_id"]) if incident_row else ""
        await conn.close()
    except Exception as dbe:
        logger.error(f"Database lookup failed during resume: {dbe}")
        raise HTTPException(status_code=500, detail="Database access error")

    if req.approved:
        # Trigger Celery execution
        task_payload = {
            "task_id": str(uuid.uuid4()),
            "workflow_id": req.workflow_id,
            "step_id": req.step_id,
            "incident_id": incident_id,
            "action": json.loads(step_row["action"]),
            "context": {},
            "permissions": []
        }
        celery_execute_step.delay(task_payload)
        return {"status": "resumed"}
    else:
        # Report rejection
        if True:
            try:
                await post(
                    f"{COORDINATOR_URL}/coordinator/step-failed",
                    json={
                        "task_id": str(uuid.uuid4()),
                        "step_id": req.step_id,
                        "workflow_id": req.workflow_id,
                        "incident_id": incident_id,
                        "error": f"Step manual approval rejected. Reason: {req.reason or 'No reason provided'}"
                    }
                )
            except Exception as ce:
                logger.error(f"Failed to report manual rejection to Coordinator: {ce}")
        return {"status": "rejected"}

async def restore_in_progress_workflows():
    # Wait a moment for dependency services to boot
    await asyncio.sleep(2.0)
    logger.info("Starting workflow state restoration routine...")
    
    memory_url = os.environ.get("MEMORY_AGENT_URL", "http://memory-agent:8017")
    observability_url = os.environ.get("OBSERVABILITY_URL", "http://observability-service:8040")
    
    if True:
        try:
            res = await get(f"{memory_url}/memory/workflows?status=planning,executing,suspended")
            if res.status_code != 200:
                logger.error(f"Failed to query Memory Agent for active workflows: {res.text}")
                return
                
            active_workflows = res.json()
            logger.info(f"Found {len(active_workflows)} workflows in non-terminal states to restore.")
            
            import asyncpg
            import redis.asyncio as redis_async
            
            for wf in active_workflows:
                workflow_id = wf["id"]
                incident_id = wf["incident_id"]
                
                # Fetch active/suspended steps
                try:
                    conn = await asyncpg.connect(DATABASE_URL)
                    rows = await conn.fetch(
                        "SELECT id, agent_type, action, status FROM workflow_steps WHERE workflow_id = $1 AND status IN ('active', 'suspended')",
                        uuid.UUID(workflow_id)
                    )
                    await conn.close()
                except Exception as dbe:
                    logger.error(f"Error querying active steps for workflow {workflow_id}: {dbe}")
                    continue
                    
                for step in rows:
                    step_id = str(step["id"])
                    agent_type = step["agent_type"]
                    action_data = json.loads(step["action"])
                    status_str = step["status"]
                    
                    if status_str == "active":
                        # Re-enqueue the active step to its Redis channel
                        logger.info(f"Re-enqueuing active step {step_id} of agent type {agent_type} to agent channel")
                        task_payload = {
                            "task_id": str(uuid.uuid4()),
                            "workflow_id": workflow_id,
                            "step_id": step_id,
                            "incident_id": incident_id,
                            "action": action_data,
                            "context": {},
                            "permissions": []
                        }
                        try:
                            r_client = redis_async.from_url(REDIS_URL)
                            await r_client.publish(f"agent:{agent_type}:tasks", json.dumps(task_payload))
                            await r_client.close()
                        except Exception as re:
                            logger.error(f"Failed to publish re-enqueue event to Redis for step {step_id}: {re}")
                            
                # Emit event to Observability
                try:
                    await post(
                        f"{observability_url}/observability/events",
                        json={
                            "type": "workflow.restored",
                            "sequence": 1,
                            "payload": {
                                "workflow_id": workflow_id,
                                "incident_id": incident_id,
                                "status": wf["status"]
                            },
                            "emitted_at": datetime_now_iso()
                        }
                    )
                    logger.info(f"Emitted workflow.restored event for {workflow_id}")
                except Exception as oe:
                    logger.error(f"Failed to emit workflow.restored event: {oe}")
                    
        except Exception as e:
            logger.error(f"Error in restore_in_progress_workflows: {str(e)}")

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(restore_in_progress_workflows())

@app.get("/health")
async def health():
    return {"status": "healthy", "service": "workflow-engine"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8030)
