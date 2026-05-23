import uuid
import json
import logging
from datetime import datetime, timezone
import asyncpg

logger = logging.getLogger("observability-service.trace_builder")

async def build_execution_trace(workflow_id: str, database_url: str) -> dict:
    if not database_url:
        raise ValueError("database_url is required")
        
    wf_uuid = uuid.UUID(workflow_id)
    conn = await asyncpg.connect(database_url)
    try:
        # 1. Fetch workflow metadata
        wf = await conn.fetchrow(
            "SELECT id, incident_id, plan, status, current_step_ids, checkpoint, retry_count, created_at, updated_at FROM workflows WHERE id = $1",
            wf_uuid
        )
        if not wf:
            return {"error": "Workflow not found"}
            
        wf_dict = dict(wf)
        if isinstance(wf_dict.get("plan"), str):
            wf_dict["plan"] = json.loads(wf_dict["plan"])
        if isinstance(wf_dict.get("checkpoint"), str):
            wf_dict["checkpoint"] = json.loads(wf_dict["checkpoint"])
            
        # 2. Fetch steps
        steps = await conn.fetch(
            "SELECT id, workflow_id, agent_type, action, status, depends_on, output, retry_count, created_at, updated_at FROM workflow_steps WHERE workflow_id = $1 ORDER BY created_at ASC",
            wf_uuid
        )
        
        steps_list = []
        for step in steps:
            s_dict = dict(step)
            if isinstance(s_dict.get("action"), str):
                s_dict["action"] = json.loads(s_dict["action"])
            if isinstance(s_dict.get("output"), str):
                s_dict["output"] = json.loads(s_dict["output"])
            steps_list.append(s_dict)
            
        # 3. Fetch audit logs
        logs = await conn.fetch(
            "SELECT id, event_type, timestamp, agent_identity, incident_id, workflow_id, action_description, inputs, outputs, risk_score FROM audit_trail WHERE workflow_id = $1 ORDER BY timestamp ASC, id ASC",
            wf_uuid
        )
        
        logs_list = []
        for log in logs:
            l_dict = dict(log)
            if isinstance(l_dict.get("inputs"), str):
                l_dict["inputs"] = json.loads(l_dict["inputs"])
            if isinstance(l_dict.get("outputs"), str):
                l_dict["outputs"] = json.loads(l_dict["outputs"])
            logs_list.append(l_dict)
            
        # 4. Construct response
        trace = {
            "workflow": {
                "id": str(wf_uuid),
                "incident_id": str(wf_dict.get("incident_id")),
                "status": wf_dict.get("status"),
                "current_step_ids": [str(sid) for sid in (wf_dict.get("current_step_ids") or [])],
                "retry_count": wf_dict.get("retry_count"),
                "created_at": wf_dict.get("created_at").isoformat() if wf_dict.get("created_at") else None,
                "updated_at": wf_dict.get("updated_at").isoformat() if wf_dict.get("updated_at") else None,
            },
            "steps": [
                {
                    "id": str(s["id"]),
                    "agent_type": s["agent_type"],
                    "action": s["action"],
                    "status": s["status"],
                    "depends_on": [str(d) for d in (s["depends_on"] or [])],
                    "output": s["output"],
                    "retry_count": s["retry_count"],
                    "created_at": s["created_at"].isoformat() if s["created_at"] else None,
                    "updated_at": s["updated_at"].isoformat() if s["updated_at"] else None,
                }
                for s in steps_list
            ],
            "audit_logs": [
                {
                    "id": l["id"],
                    "event_type": l["event_type"],
                    "timestamp": l["timestamp"].isoformat() if l["timestamp"] else None,
                    "agent_identity": l["agent_identity"],
                    "action_description": l["action_description"],
                    "inputs": l["inputs"],
                    "outputs": l["outputs"],
                    "risk_score": l["risk_score"]
                }
                for l in logs_list
            ]
        }
        
        # 5. Completeness check on terminal status
        if wf_dict.get("status") in ["completed", "failed"]:
            # A complete execution trace requires at least some steps and logs.
            # If steps or logs are missing, warn.
            missing = []
            if not trace["steps"]:
                missing.append("steps")
            if not trace["audit_logs"]:
                missing.append("audit_logs")
                
            # Check that every step has an execution log
            step_ids_with_logs = {str(l["inputs"].get("step_id")) for l in trace["audit_logs"] if l["inputs"] and "step_id" in l["inputs"]}
            for step in trace["steps"]:
                if step["id"] not in step_ids_with_logs:
                    missing.append(f"audit_log_for_step_{step['id']}")
                    
            if missing:
                logger.warning(f"Workflow {workflow_id} trace completeness check failed. Missing: {missing}")
                trace["completeness_warning"] = f"Missing components: {missing}"
            else:
                trace["completeness_warning"] = None
                
        return trace
    finally:
        await conn.close()
