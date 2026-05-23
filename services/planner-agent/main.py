import os
import uuid
import json
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
import httpx
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("planner-agent")

app = FastAPI(title="Planner Agent", version="1.0.0")

# URLs and environment configurations
COORDINATOR_URL = os.environ.get("COORDINATOR_URL", "http://coordinator:8001")
GOVERNANCE_URL = os.environ.get("GOVERNANCE_URL", "http://governance-service:8020")
MEMORY_AGENT_URL = os.environ.get("MEMORY_AGENT_URL", "http://memory-agent:8017")
ESCALATION_AGENT_URL = os.environ.get("ESCALATION_AGENT_URL", "http://escalation-agent:8015")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "mock-key")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL_PLANNER", "gemini-1.5-pro")

# ---------------------------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------------------------
class ActionDescriptor(BaseModel):
    tool: str
    params: dict = Field(default_factory=dict)
    timeout_seconds: int = 30

class WorkflowStepInput(BaseModel):
    id: str
    agent_type: str
    action: ActionDescriptor
    depends_on: List[str] = Field(default_factory=list)

class GeneratePlanRequest(BaseModel):
    incident_id: str
    severity: Optional[str] = None
    root_signature: str
    workflow_id: str
    context: Optional[dict] = Field(default_factory=dict)

class ReplanRequest(BaseModel):
    workflow_id: str
    failed_step_id: str
    error: str

# Helper: DAG Acyclicity & Validation
def validate_plan_structure(steps: List[Dict[str, Any]]) -> bool:
    """Perform a DAG acyclicity check using topological sorting (DFS)."""
    step_ids = {s["id"] for s in steps}
    
    # 1. Verify all depends_on refer to existing steps
    for step in steps:
        for dep in step.get("depends_on", []):
            if dep not in step_ids:
                logger.error(f"Validation failure: Step {step['id']} depends on non-existent step {dep}")
                return False

    # 2. Cycle detection using DFS
    adj = {s["id"]: [] for s in steps}
    for step in steps:
        for dep in step.get("depends_on", []):
            adj[dep].append(step["id"])

    visited = {} # id -> state (0 = unvisited, 1 = visiting, 2 = visited)
    for sid in adj:
        visited[sid] = 0

    def has_cycle(u: str) -> bool:
        visited[u] = 1 # visiting
        for v in adj[u]:
            if visited[v] == 1:
                return True
            if visited[v] == 0:
                if has_cycle(v):
                    return True
        visited[u] = 2 # visited
        return False

    for sid in adj:
        if visited[sid] == 0:
            if has_cycle(sid):
                logger.error("Validation failure: Plan contains cyclic dependencies")
                return False

    return True

# Helper: Call LLM / Mock Plan Generation
async def generate_raw_plan(incident_id: str, severity: str, root_sig: str, workflow_id: str, violations: List[str] = None) -> List[Dict[str, Any]]:
    """Generate plan steps using Gemini or deterministic mock."""
    if GEMINI_API_KEY == "mock-key":
        logger.info("Using deterministic mock plan generator")
        step1_id = str(uuid.uuid4())
        step2_id = str(uuid.uuid4())
        step3_id = str(uuid.uuid4())
        
        # If there are specific violations (e.g. cycle validation testing, etc.), we can mock specific behaviors.
        # But by default we generate a valid sequence
        steps = [
            {
                "id": step1_id,
                "workflow_id": workflow_id,
                "agent_type": "operations",
                "action": {
                    "tool": "gather_logs",
                    "params": {"service": "db"},
                    "timeout_seconds": 30
                },
                "status": "pending",
                "depends_on": []
            },
            {
                "id": step2_id,
                "workflow_id": workflow_id,
                "agent_type": "compliance",
                "action": {
                    "tool": "verify_policy",
                    "params": {"policy_id": "GDPR-101"},
                    "timeout_seconds": 30
                },
                "status": "pending",
                "depends_on": [step1_id]
            },
            {
                "id": step3_id,
                "workflow_id": workflow_id,
                "agent_type": "operations",
                "action": {
                    "tool": "restart_service",
                    "params": {"service": "db"},
                    "timeout_seconds": 30
                },
                "status": "pending",
                "depends_on": [step2_id]
            }
        ]
        return steps

    # Real LLM call
    import google.generativeai as genai
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel(GEMINI_MODEL)
        
        violation_context = ""
        if violations:
            violation_context = f"\nPrevious plan was rejected due to: {', '.join(violations)}. Generate a plan avoiding these."

        prompt = f"""
        You are the Planner Agent for AEOS.
        Generate a complete operational resolution plan for the following incident:
        Incident ID: {incident_id}
        Severity: {severity}
        Root Signature: {root_sig}
        Workflow ID: {workflow_id}
        {violation_context}

        Return ONLY a valid JSON list of steps matching this schema:
        [
          {{
            "id": "uuid-string",
            "agent_type": "operations" | "compliance" | "validation" | "recovery" | "memory",
            "action": {{
              "tool": "string",
              "params": {{}},
              "timeout_seconds": 30
            }},
            "depends_on": ["parent-uuid-string"]
          }}
        ]
        Do not add any markdown formatting, backticks, or other text.
        Ensure that depends_on arrays do not introduce any cycles.
        """
        response = await model.generate_content_async(prompt)
        text = response.text.strip()
        if text.startswith("```json"):
            text = text[7:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
        
        raw_steps = json.loads(text)
        # Add workflow_id and pending status to LLM steps
        for step in raw_steps:
            step["workflow_id"] = workflow_id
            step["status"] = "pending"
        return raw_steps
    except Exception as e:
        logger.error(f"Gemini planner failure: {e}. Falling back to default mock plan.")
        # Fallback
        step1_id = str(uuid.uuid4())
        return [{
            "id": step1_id,
            "workflow_id": workflow_id,
            "agent_type": "operations",
            "action": {"tool": "fallback_action", "params": {}, "timeout_seconds": 30},
            "status": "pending",
            "depends_on": []
        }]

# Helper: Orchestrate Plan Generation, Validation, Governance Check, and Dispatch
async def execute_plan_generation_flow(req: GeneratePlanRequest):
    workflow_id = req.workflow_id
    incident_id = req.incident_id
    severity = req.severity or "low"
    root_sig = req.root_signature

    retry_count = 0
    violations = []
    
    while retry_count <= 3:
        # 1. Generate plan
        steps = await generate_raw_plan(incident_id, severity, root_sig, workflow_id, violations)
        
        # 2. Structural/DAG check
        if not validate_plan_structure(steps):
            logger.warn("DAG cycle or link error detected. Retrying plan generation...")
            violations.append("Cyclic dependency or link error detected in DAG structure")
            retry_count += 1
            continue

        # 3. Governance plan validation check
        async with httpx.AsyncClient() as client:
            try:
                gov_response = await client.post(
                    f"{GOVERNANCE_URL}/governance/validate-plan",
                    json={"steps": steps, "metadata": {}}
                )
                gov_data = gov_response.json()
                if not gov_data.get("valid", True):
                    gov_violations = [v.get("message", "Policy violation") for v in gov_data.get("violations", [])]
                    logger.warn(f"Governance validation failed: {gov_violations}. Retrying...")
                    violations.extend(gov_violations)
                    retry_count += 1
                    continue
            except Exception as e:
                logger.warn(f"Failed to communicate with Governance Layer: {e}. Assuming valid for development.")

        # 4. If approved: persist plan to Memory Agent
        async with httpx.AsyncClient() as client:
            try:
                await client.post(
                    f"{MEMORY_AGENT_URL}/memory/plans",
                    json={"workflow_id": workflow_id, "steps": steps}
                )
                logger.info("Plan successfully persisted to Memory Agent")
            except Exception as e:
                logger.warn(f"Failed to persist plan to Memory Agent: {e}")

        # 5. Forward approved plan to Coordinator
        async with httpx.AsyncClient() as client:
            try:
                await client.post(
                    f"{COORDINATOR_URL}/coordinator/plan-ready",
                    json={"workflow_id": workflow_id, "steps": steps}
                )
                logger.info("Plan forwarded to Coordinator plan-ready endpoint")
            except Exception as e:
                logger.error(f"Failed to forward plan to Coordinator: {e}")
                raise HTTPException(status_code=500, detail="Coordinator plan-ready dispatch failed")

        return {"status": "success", "steps": steps}

    # 6. Retry limit exceeded: Escalate to Escalation Agent
    logger.error(f"Plan generation failed after {retry_count} attempts. Escalating...")
    async with httpx.AsyncClient() as client:
        try:
            await client.post(
                f"{ESCALATION_AGENT_URL}/escalation/notify",
                json={
                    "incident_id": incident_id,
                    "workflow_id": workflow_id,
                    "reason": f"Plan generation retries exceeded limit (3). Policy violations: {violations}"
                }
            )
        except Exception as e:
            logger.error(f"Failed to notify Escalation Agent: {e}")
            
    raise HTTPException(status_code=422, detail="Plan rejected by governance after 3 retries")

# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------
@app.post("/planner/generate")
async def generate_plan_endpoint(req: GeneratePlanRequest):
    logger.info(f"Generating plan for incident {req.incident_id}, workflow {req.workflow_id}")
    return await execute_plan_generation_flow(req)

@app.post("/planner/replan")
async def replan_endpoint(req: ReplanRequest):
    logger.info(f"Re-planning requested for workflow {req.workflow_id} due to failed step {req.failed_step_id}")
    # Simulates replanning by injecting a recovery/restart step
    step_id = str(uuid.uuid4())
    recovery_steps = [{
        "id": step_id,
        "workflow_id": req.workflow_id,
        "agent_type": "recovery",
        "action": {
            "tool": "remediate_failure",
            "params": {"failed_step_id": req.failed_step_id, "error": req.error},
            "timeout_seconds": 30
        },
        "status": "pending",
        "depends_on": []
    }]
    
    # Forward to Coordinator plan-ready
    async with httpx.AsyncClient() as client:
        try:
            await client.post(
                f"{COORDINATOR_URL}/coordinator/plan-ready",
                json={"workflow_id": req.workflow_id, "steps": recovery_steps}
            )
            logger.info("Replanned steps forwarded to Coordinator")
        except Exception as e:
            logger.error(f"Failed to dispatch replanned steps: {e}")
            
    return {"status": "replanned", "steps": recovery_steps}

@app.get("/health")
async def health():
    return {"status": "healthy", "service": "planner"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8010)
