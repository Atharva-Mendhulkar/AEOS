import os
import json
import uuid
import logging
import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
import httpx
import asyncpg
import redis.asyncio as redis

# Import custom sub-modules
from scoring.rule_based import evaluate_rule_based_risk, RiskAssessment
from scoring.llm_based import evaluate_llm_risk
from permissions.enforcer import check_permission, load_permissions_to_cache
from policies.hot_reload import start_hot_reload_listener
from anomaly.detector import record_action_and_detect_anomalies

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("governance-service")

app = FastAPI(title="Governance Service", version="1.0.0")

# Service URLs
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/aeos")
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
MEMORY_AGENT_URL = os.environ.get("MEMORY_AGENT_URL", "http://memory-agent:8017")
OBSERVABILITY_URL = os.environ.get("OBSERVABILITY_URL", "http://observability-service:8040")
ESCALATION_AGENT_URL = os.environ.get("ESCALATION_AGENT_URL", "http://escalation-agent:8015")
COORDINATOR_URL = os.environ.get("COORDINATOR_URL", "http://coordinator:8001")

# Pydantic Request Models
class ActionDescriptor(BaseModel):
    tool: str
    params: dict = Field(default_factory=dict)
    timeout_seconds: int = 30

class ValidateActionRequest(BaseModel):
    action: ActionDescriptor
    agent_type: str
    incident_id: Optional[str] = None
    workflow_id: Optional[str] = None

class ValidatePlanRequest(BaseModel):
    steps: List[dict]
    metadata: dict = Field(default_factory=dict)

class PolicyConfig(BaseModel):
    name: str
    policy_type: str
    config: dict
    created_by: str = "system"
    is_active: bool = True

def datetime_now_iso():
    return datetime.now(timezone.utc).isoformat()

# ---------------------------------------------------------------------------
# Policy JSON Validation Schema
# ---------------------------------------------------------------------------
def validate_policy_json(policy_type: str, config: dict):
    """Validate policy JSON schema configuration."""
    if policy_type == "permission":
        agent_type = config.get("agent_type")
        if not agent_type:
            raise HTTPException(status_code=422, detail="Permission policy must specify 'agent_type'")
        # Ensure at least one permission rule is present
        allowed_res = config.get("allowed_resources")
        denied_res = config.get("denied_resources")
        allowed_t = config.get("allowed_tools")
        denied_t = config.get("denied_tools")
        if all(x is None for x in [allowed_res, denied_res, allowed_t, denied_t]):
            raise HTTPException(
                status_code=422, 
                detail="Permission policy config must specify allowed_resources, denied_resources, allowed_tools, or denied_tools"
            )
        for key in ["allowed_resources", "denied_resources", "allowed_tools", "denied_tools"]:
            val = config.get(key)
            if val is not None and not isinstance(val, list):
                raise HTTPException(status_code=422, detail=f"Permission key '{key}' must be a list of strings")

    elif policy_type == "anomaly":
        max_freq = config.get("max_frequency_per_minute")
        if max_freq is not None:
            if not isinstance(max_freq, (int, float)) or max_freq <= 0:
                raise HTTPException(status_code=422, detail="max_frequency_per_minute must be a positive number")
        max_consec = config.get("max_consecutive_identical_actions")
        if max_consec is not None:
            if not isinstance(max_consec, int) or max_consec <= 0:
                raise HTTPException(status_code=422, detail="max_consecutive_identical_actions must be a positive integer")

    elif policy_type == "risk_threshold":
        suspend_threshold = config.get("suspend_threshold")
        halt_threshold = config.get("halt_threshold")
        if suspend_threshold is not None:
            if not isinstance(suspend_threshold, (int, float)) or not (0.0 <= suspend_threshold <= 10.0):
                raise HTTPException(status_code=422, detail="suspend_threshold must be a float between 0.0 and 10.0")
        if halt_threshold is not None:
            if not isinstance(halt_threshold, (int, float)) or not (0.0 <= halt_threshold <= 10.0):
                raise HTTPException(status_code=422, detail="halt_threshold must be a float between 0.0 and 10.0")
            if suspend_threshold is not None and suspend_threshold > halt_threshold:
                raise HTTPException(status_code=422, detail="suspend_threshold cannot exceed halt_threshold")

    elif policy_type == "retention":
        days = config.get("retention_days")
        if days is None or not isinstance(days, int) or days <= 0:
            raise HTTPException(status_code=422, detail="retention_days must be a positive integer")
    else:
        raise HTTPException(status_code=422, detail=f"Unsupported policy_type: '{policy_type}'")

# Helper to publish policy reload signal to Redis
async def trigger_policy_reload(policy_name: str):
    r = redis.from_url(REDIS_URL)
    try:
        await r.publish("policy:updated", f"Policy '{policy_name}' updated")
    except Exception as e:
        logger.error(f"Failed to publish update notification to Redis: {e}")

# Helper to record event in Memory Agent Audit Trail
async def record_audit_entry(agent: str, event_type: str, desc: str, inputs: dict, outputs: dict, incident_id: Optional[str] = None, workflow_id: Optional[str] = None, risk: Optional[float] = None):
    audit_payload = {
        "event_type": event_type,
        "timestamp": datetime_now_iso(),
        "agent_identity": agent,
        "incident_id": incident_id,
        "workflow_id": workflow_id,
        "action_description": desc,
        "inputs": inputs,
        "outputs": outputs,
        "risk_score": risk
    }
    async with httpx.AsyncClient() as client:
        try:
            await client.post(f"{MEMORY_AGENT_URL}/memory/audit", json=audit_payload)
        except Exception as e:
            logger.error(f"Failed to write to Audit Trail: {e}")

# Helper to emit circuit breaker event
async def emit_circuit_breaker_activated(agent: str, incident_id: Optional[str], workflow_id: Optional[str], score: float):
    event_payload = {
        "event_type": "circuit_breaker.activated",
        "timestamp": datetime_now_iso(),
        "agent_identity": agent,
        "action_description": f"Governance Circuit Breaker activated due to extreme risk ({score})",
        "incident_id": incident_id,
        "workflow_id": workflow_id
    }
    async with httpx.AsyncClient() as client:
        try:
            await client.post(f"{OBSERVABILITY_URL}/observability/events", json=event_payload)
        except Exception as e:
            logger.error(f"Failed to emit circuit breaker event: {e}")

# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------

@app.post("/governance/validate-action")
async def validate_action(req: ValidateActionRequest):
    action_dict = req.action.model_dump()
    logger.info(f"Validating action: {req.action.tool} for agent {req.agent_type}")

    # 1. Permission Gating check (before risk scoring)
    perm_res = await check_permission(req.agent_type, action_dict)
    if not perm_res.allowed:
        logger.error(f"Permission denied: {perm_res.reason}")
        # Audit denial
        await record_audit_entry(
            agent=req.agent_type,
            event_type="governance.denied",
            desc=f"Permission Denied executing action {req.action.tool}",
            inputs={"action": action_dict},
            outputs={"approved": False, "reason": perm_res.reason},
            incident_id=req.incident_id,
            workflow_id=req.workflow_id,
            risk=10.0
        )
        return {
            "approved": False,
            "status": "denied",
            "risk_score": 10.0,
            "scoring_method": "permission_check",
            "factors": [perm_res.reason]
        }

    # 2. Risk Evaluation
    # Evaluate using rule-based scoring first
    rule_res = evaluate_rule_based_risk(action_dict)
    
    if rule_res.scoring_method == "rule_based" and rule_res.factors and "Base risk for unknown" in rule_res.factors[0]:
        # Fall back to LLM-based scoring if action type was unknown/unmatched
        logger.info("Rule-based matched unknown action type. Falling back to LLM scoring...")
        risk_res = await evaluate_llm_risk(action_dict, req.agent_type)
    else:
        risk_res = rule_res

    score = risk_res.score
    factors = risk_res.factors
    method = risk_res.scoring_method

    # 3. Decision Gating
    approved = True
    status_str = "executing"
    
    if score >= 9.0:
        # Circuit Breaker Gating
        approved = False
        status_str = "halted"
        logger.error(f"Circuit breaker activated (risk: {score}) for action {req.action.tool}")
        # Emit circuit breaker event
        await emit_circuit_breaker_activated(req.agent_type, req.incident_id, req.workflow_id, score)
    elif score >= 7.0:
        # Approval Gate Gating
        approved = True
        status_str = "suspended"
        logger.warn(f"Approval gate triggered (risk: {score}) for action {req.action.tool}")
        
    # 4. Async Anomaly check registration
    asyncio.create_task(record_action_and_detect_anomalies(req.agent_type, action_dict))

    # 5. Audit Logging
    await record_audit_entry(
        agent=req.agent_type,
        event_type="governance.validation",
        desc=f"Validate action {req.action.tool}",
        inputs={"action": action_dict},
        outputs={"approved": approved, "status": status_str, "risk_score": score, "factors": factors},
        incident_id=req.incident_id,
        workflow_id=req.workflow_id,
        risk=score
    )

    return {
        "approved": approved,
        "status": status_str,
        "risk_score": score,
        "scoring_method": method,
        "factors": factors
    }

@app.post("/governance/validate-plan")
async def validate_plan(req: ValidatePlanRequest):
    violations = []
    
    for step in req.steps:
        step_id = step.get("id") or str(uuid.uuid4())
        agent_type = step.get("agent_type", "operations")
        action = step.get("action", {})
        
        # 1. Run permission check
        perm_res = await check_permission(agent_type, action)
        if not perm_res.allowed:
            violations.append({
                "step_id": step_id,
                "violation": perm_res.reason
            })
            continue

        # 2. Run risk assessment
        rule_res = evaluate_rule_based_risk(action)
        if rule_res.scoring_method == "rule_based" and rule_res.factors and "Base risk for unknown" in rule_res.factors[0]:
            risk_res = await evaluate_llm_risk(action, agent_type)
        else:
            risk_res = rule_res
            
        if risk_res.score >= 9.0:
            violations.append({
                "step_id": step_id,
                "violation": f"Circuit breaker risk threshold exceeded: {risk_res.score} (Factors: {', '.join(risk_res.factors)})"
            })

    valid = len(violations) == 0
    return {
        "valid": valid,
        "violations": violations
    }

# ---------------------------------------------------------------------------
# Policy CRUD Endpoints
# ---------------------------------------------------------------------------

@app.get("/governance/policies")
async def get_policies():
    try:
        conn = await asyncpg.connect(DATABASE_URL)
        rows = await conn.fetch("SELECT id, name, version, is_active, policy_type, config, created_by, created_at, updated_at FROM policies ORDER BY updated_at DESC")
        await conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"Failed to fetch policies: {e}")
        raise HTTPException(status_code=500, detail="Database access error")

@app.post("/governance/policies", status_code=status.HTTP_201_CREATED)
async def create_policy(policy: PolicyConfig):
    # Validate JSON Schema
    validate_policy_json(policy.policy_type, policy.config)
    
    try:
        conn = await asyncpg.connect(DATABASE_URL)
        # Check name constraint
        existing = await conn.fetchrow("SELECT id FROM policies WHERE name = $1", policy.name)
        if existing:
            await conn.close()
            raise HTTPException(status_code=400, detail=f"Policy name '{policy.name}' already exists")
            
        # Insert
        row = await conn.fetchrow(
            """INSERT INTO policies (name, version, is_active, policy_type, config, created_by, created_at, updated_at) 
               VALUES ($1, 1, $2, $3, $4, $5, NOW(), NOW()) RETURNING id, version""",
            policy.name, policy.is_active, policy.policy_type, json.dumps(policy.config), policy.created_by
        )
        await conn.close()
        
        # Publish hot-reload signal
        await trigger_policy_reload(policy.name)
        
        # Audit policy creation
        new_id = str(row["id"])
        await record_audit_entry(
            agent="governance",
            event_type="policy.created",
            desc=f"Policy '{policy.name}' (type: {policy.policy_type}, version: 1) created by {policy.created_by}",
            inputs={"policy_config": policy.config},
            outputs={"policy_id": new_id, "version": 1}
        )
        
        return {
            "policy_id": new_id,
            "version": 1,
            "status": "created"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create policy: {e}")
        raise HTTPException(status_code=500, detail=f"Database write error: {e}")

@app.put("/governance/policies/{policy_id}")
async def update_policy(policy_id: str, req_data: dict):
    # Check UUID
    try:
        pid = uuid.UUID(policy_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")

    try:
        conn = await asyncpg.connect(DATABASE_URL)
        existing = await conn.fetchrow(
            "SELECT name, policy_type, version, config FROM policies WHERE id = $1", pid
        )
        if not existing:
            await conn.close()
            raise HTTPException(status_code=404, detail="Policy not found")
            
        policy_type = req_data.get("policy_type") or existing["policy_type"]
        config = req_data.get("config") or json.loads(existing["config"])
        name = req_data.get("name") or existing["name"]
        is_active = req_data.get("is_active") if req_data.get("is_active") is not None else True
        operator = req_data.get("created_by") or "system"

        # Validate configuration JSON schema
        validate_policy_json(policy_type, config)

        new_version = existing["version"] + 1

        # Update SQL
        await conn.execute(
            """UPDATE policies 
               SET name = $1, version = $2, is_active = $3, policy_type = $4, config = $5, created_by = $6, updated_at = NOW()
               WHERE id = $7""",
            name, new_version, is_active, policy_type, json.dumps(config), operator, pid
        )
        await conn.close()

        # Publish hot-reload trigger
        await trigger_policy_reload(name)

        # Audit policy modification
        await record_audit_entry(
            agent="governance",
            event_type="policy.updated",
            desc=f"Policy '{name}' (type: {policy_type}) updated to version {new_version} by {operator}",
            inputs={"policy_config": config},
            outputs={"policy_id": policy_id, "version": new_version}
        )

        return {
            "policy_id": policy_id,
            "version": new_version,
            "status": "updated"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update policy {policy_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Database update failure: {e}")

@app.get("/health")
async def health():
    return {"status": "healthy", "service": "governance"}

# Startup configuration
@app.on_event("startup")
async def startup_event():
    logger.info("Initializing Governance Service cache and starting pub-sub listener...")
    # Initial load of postgres permission cache to Redis
    await load_permissions_to_cache()
    # Spawn background hot-reload daemon
    asyncio.create_task(start_hot_reload_listener())

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8020)
