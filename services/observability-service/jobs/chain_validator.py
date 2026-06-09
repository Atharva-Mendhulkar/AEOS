import hashlib
import json
from datetime import datetime, timezone
import uuid
import asyncpg
import logging

logger = logging.getLogger("observability-service.chain_validator")

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

async def validate_chain(from_id: int = None, to_id: int = None, database_url: str = None) -> dict:
    if not database_url:
        raise ValueError("database_url is required")
        
    conn = await asyncpg.connect(database_url)
    try:
        query = "SELECT id, event_type, timestamp, agent_identity, incident_id, workflow_id, action_description, inputs, outputs, risk_score, prev_entry_hash FROM audit_trail"
        conditions = []
        params = []
        if from_id is not None:
            params.append(from_id)
            conditions.append(f"id >= ${len(params)}")
        if to_id is not None:
            params.append(to_id)
            conditions.append(f"id <= ${len(params)}")
            
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY id ASC"
        
        rows = await conn.fetch(query, *params)
        if not rows:
            return {"status": "valid", "validated_count": 0}
            
        first_row_id = rows[0]["id"]
        prev_hash = "genesis"
        
        # To verify the first row's prev_entry_hash, fetch the row right before it if it exists.
        if first_row_id > 1:
            prev_row = await conn.fetchrow(
                """
                SELECT event_type, timestamp, agent_identity, incident_id, workflow_id, 
                       action_description, inputs, outputs, risk_score, prev_entry_hash
                FROM audit_trail 
                WHERE id < $1 
                ORDER BY id DESC 
                LIMIT 1
                """, 
                first_row_id
            )
            if prev_row:
                p_dict = dict(prev_row)
                if isinstance(p_dict.get("inputs"), str):
                    p_dict["inputs"] = json.loads(p_dict["inputs"])
                if isinstance(p_dict.get("outputs"), str):
                    p_dict["outputs"] = json.loads(p_dict["outputs"])
                prev_hash = compute_entry_hash(p_dict)
            else:
                # Retention can drop older partitions. In that case the first
                # retained row is the validation anchor for the remaining window.
                prev_hash = rows[0]["prev_entry_hash"]
                
        for row in rows:
            r_dict = dict(row)
            if isinstance(r_dict.get("inputs"), str):
                r_dict["inputs"] = json.loads(r_dict["inputs"])
            if isinstance(r_dict.get("outputs"), str):
                r_dict["outputs"] = json.loads(r_dict["outputs"])
                
            stored_prev_hash = r_dict.get("prev_entry_hash")
            if stored_prev_hash != prev_hash:
                logger.error(f"Audit trail tampered! ID: {r_dict['id']}. Expected: {prev_hash}, Actual: {stored_prev_hash}")
                return {
                    "status": "tampered",
                    "compromised_id": r_dict["id"],
                    "expected": prev_hash,
                    "actual": stored_prev_hash
                }
            prev_hash = compute_entry_hash(r_dict)
            
        return {"status": "valid", "validated_count": len(rows)}
    except Exception as e:
        logger.error(f"Error during chain validation: {e}")
        return {"status": "error", "message": str(e)}
    finally:
        await conn.close()
