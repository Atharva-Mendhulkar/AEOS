import os
import json
import time
import logging
import httpx
import asyncpg
import redis.asyncio as redis
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

logger = logging.getLogger("governance-anomaly")

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/aeos")
OBSERVABILITY_URL = os.environ.get("OBSERVABILITY_URL", "http://observability-service:8040")

# Lazy Redis client helper
redis_client = None

def get_redis_client():
    global redis_client
    if redis_client is None:
        redis_client = redis.from_url(REDIS_URL, decode_responses=True)
    return redis_client

async def get_anomaly_policy() -> Dict[str, Any]:
    """Load active anomaly policy config."""
    try:
        conn = await asyncpg.connect(DATABASE_URL)
        row = await conn.fetchrow(
            "SELECT config FROM policies WHERE policy_type = 'anomaly' AND is_active = TRUE"
        )
        await conn.close()
        if row:
            return json.loads(row["config"])
    except Exception as e:
        logger.error(f"Failed to query anomaly policy from PostgreSQL: {e}")
    
    # Standard default fallback policy configuration
    return {
        "max_frequency_per_minute": 30,
        "max_consecutive_identical_actions": 5,
        "frequency_time_window_seconds": 60
    }

async def record_action_and_detect_anomalies(agent_type: str, action: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Records the action in Redis history and checks for pattern anomalies."""
    r = get_redis_client()
    history_key = f"governance:agent:{agent_type}:history"
    
    now = time.time()
    tool = action.get("tool", "")
    params = action.get("params", {})
    resource = params.get("resource") or params.get("service") or params.get("service_name") or params.get("target") or "unknown"
    
    new_entry = {
        "timestamp": now,
        "tool": tool,
        "resource": resource
    }
    
    try:
        # Push to rolling log and trim to 1000 items
        await r.lpush(history_key, json.dumps(new_entry))
        await r.ltrim(history_key, 0, 999)
        
        # Load recent actions to evaluate against baseline config
        history_raw = await r.lrange(history_key, 0, 100)
        history = [json.loads(x) for x in history_raw]
    except Exception as re:
        logger.error(f"Redis operation failed during anomaly check: {re}")
        return None

    policy = await get_anomaly_policy()
    
    # 1. Action Frequency Check
    window = policy.get("frequency_time_window_seconds", 60)
    max_freq = policy.get("max_frequency_per_minute", 30)
    
    actions_in_window = [h for h in history if now - h["timestamp"] <= window]
    freq = len(actions_in_window)
    
    if freq > max_freq:
        deviation = (freq - max_freq) / max_freq
        description = f"Agent '{agent_type}' execution frequency ({freq} actions) exceeded baseline limit ({max_freq}) in {window}s window."
        anomaly_info = {
            "pattern_id": "FREQ_EXCEEDED",
            "description": description,
            "baseline_deviation": deviation
        }
        await emit_anomaly_event(agent_type, action, anomaly_info)
        return anomaly_info

    # 2. Consecutive Identical Actions Check (potential loop)
    max_consecutive = policy.get("max_consecutive_identical_actions", 5)
    if len(history) >= max_consecutive:
        consecutive_count = 1
        for i in range(1, len(history)):
            if (history[i]["tool"] == tool and history[i]["resource"] == resource):
                consecutive_count += 1
            else:
                break
                
        if consecutive_count > max_consecutive:
            deviation = float(consecutive_count - max_consecutive)
            description = f"Agent '{agent_type}' executed identical tool '{tool}' on resource '{resource}' {consecutive_count} consecutive times, exceeding limits."
            anomaly_info = {
                "pattern_id": "LOOP_DETECTED",
                "description": description,
                "baseline_deviation": deviation
            }
            await emit_anomaly_event(agent_type, action, anomaly_info)
            return anomaly_info

    return None

async def emit_anomaly_event(agent_type: str, action: Dict[str, Any], anomaly_info: Dict[str, Any]):
    """Emit anomaly.detected event to the Observability service."""
    logger.warn(f"Anomaly detected! {anomaly_info['description']}")
    
    event_payload = {
        "event_type": "anomaly.detected",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "agent_identity": agent_type,
        "action_description": anomaly_info["description"],
        "inputs": {
            "action": action,
            "deviation": anomaly_info["baseline_deviation"]
        },
        "outputs": {
            "pattern_id": anomaly_info["pattern_id"]
        }
    }
    
    async with httpx.AsyncClient() as client:
        try:
            await client.post(
                f"{OBSERVABILITY_URL}/observability/events",
                json=event_payload
            )
            logger.info("Successfully emitted anomaly event to Observability Layer")
        except Exception as e:
            logger.error(f"Failed to emit anomaly event to Observability Layer: {e}")
