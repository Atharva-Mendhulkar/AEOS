import os
import json
import fnmatch
import logging
import asyncpg
import redis.asyncio as redis
from typing import Dict, Any, List, Optional

logger = logging.getLogger("governance-permissions")

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/aeos")
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

class PermissionResult:
    def __init__(self, allowed: bool, reason: str = ""):
        self.allowed = allowed
        self.reason = reason

def glob_match(val: str, patterns: List[str]) -> bool:
    """Check if value matches any glob pattern in patterns list."""
    return any(fnmatch.fnmatch(val, pattern) for pattern in patterns)

async def load_permissions_to_cache():
    """Load active permission policies from Postgres and cache in Redis."""
    try:
        conn = await asyncpg.connect(DATABASE_URL)
        rows = await conn.fetch(
            "SELECT config FROM policies WHERE policy_type = 'permission' AND is_active = TRUE"
        )
        await conn.close()
        
        r = redis.from_url(REDIS_URL, decode_responses=True)
        # Clear existing keys
        keys = await r.keys("governance:permissions:*")
        if keys:
            await r.delete(*keys)

        for row in rows:
            config = json.loads(row["config"])
            agent_type = config.get("agent_type")
            if not agent_type:
                continue
            
            cache_key = f"governance:permissions:{agent_type}"
            await r.set(cache_key, json.dumps({
                "allowed_resources": config.get("allowed_resources", []),
                "denied_resources": config.get("denied_resources", []),
                "allowed_tools": config.get("allowed_tools", []),
                "denied_tools": config.get("denied_tools", [])
            }))
        logger.info(f"Loaded {len(rows)} permission policies to Redis cache")
    except Exception as e:
        logger.error(f"Failed to load permission policies from DB: {e}")

async def get_permissions_for_agent(agent_type: str) -> Optional[Dict[str, Any]]:
    """Retrieve permissions from Redis cache, fallback to Postgres on miss."""
    r = redis.from_url(REDIS_URL, decode_responses=True)
    cache_key = f"governance:permissions:{agent_type}"
    try:
        cached = await r.get(cache_key)
        if cached:
            return json.loads(cached)
    except Exception as e:
        logger.warning(f"Redis cache lookup failed for permissions: {e}")

    # Fallback to direct Postgres lookup
    try:
        conn = await asyncpg.connect(DATABASE_URL)
        # Query active permission policy for agent_type
        # Since it's stored inside config JSONB, we query using JSONB containment or extraction
        row = await conn.fetchrow(
            "SELECT config FROM policies WHERE policy_type = 'permission' AND is_active = TRUE AND config->>'agent_type' = $1",
            agent_type
        )
        await conn.close()
        if row:
            config = json.loads(row["config"])
            perms = {
                "allowed_resources": config.get("allowed_resources", []),
                "denied_resources": config.get("denied_resources", []),
                "allowed_tools": config.get("allowed_tools", []),
                "denied_tools": config.get("denied_tools", [])
            }
            # Cache it back to Redis asynchronously
            try:
                await r.set(cache_key, json.dumps(perms))
            except Exception:
                pass
            return perms
    except Exception as e:
        logger.error(f"Postgres lookup failed for permissions: {e}")
        
    return None

async def check_permission(agent_type: str, action: Dict[str, Any]) -> PermissionResult:
    """Evaluate if the agent is permitted to execute the given action."""
    perms = await get_permissions_for_agent(agent_type)
    if not perms:
        # Default permissive if no policy is registered for this agent
        return PermissionResult(allowed=True)
        
    tool = action.get("tool", "")
    params = action.get("params", {})
    resource = params.get("resource") or params.get("service") or params.get("service_name") or params.get("target") or "unknown"
    
    # 1. Enforce allowed_tools if specified
    allowed_tools = perms.get("allowed_tools", [])
    if allowed_tools and tool not in allowed_tools:
        return PermissionResult(
            allowed=False,
            reason=f"GOVERNANCE_PERMISSION_DENIED: Tool '{tool}' is not in allowed_tools list for agent '{agent_type}'"
        )
        
    # 2. Enforce denied_tools if specified
    denied_tools = perms.get("denied_tools", [])
    if denied_tools and tool in denied_tools:
        return PermissionResult(
            allowed=False,
            reason=f"GOVERNANCE_PERMISSION_DENIED: Tool '{tool}' is explicitly denied in denied_tools list for agent '{agent_type}'"
        )
        
    # 3. Enforce allowed_resources if specified
    allowed_resources = perms.get("allowed_resources", [])
    if allowed_resources and not glob_match(resource, allowed_resources):
        return PermissionResult(
            allowed=False,
            reason=f"GOVERNANCE_PERMISSION_DENIED: Resource '{resource}' is not in allowed_resources list for agent '{agent_type}'"
        )
        
    # 4. Enforce denied_resources if specified
    denied_resources = perms.get("denied_resources", [])
    if denied_resources and glob_match(resource, denied_resources):
        return PermissionResult(
            allowed=False,
            reason=f"GOVERNANCE_PERMISSION_DENIED: Resource '{resource}' matches denied_resources list for agent '{agent_type}'"
        )
        
    return PermissionResult(allowed=True)
