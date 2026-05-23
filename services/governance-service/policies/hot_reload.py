import os
import json
import asyncio
import logging
import redis.asyncio as redis
from permissions.enforcer import load_permissions_to_cache

logger = logging.getLogger("governance-hot-reload")
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

async def start_hot_reload_listener():
    """Subscribes to Redis pub-sub to receive real-time policy reload triggers."""
    r = redis.from_url(REDIS_URL)
    pubsub = r.pubsub()
    try:
        await pubsub.subscribe("policy:updated")
        logger.info("Governance hot-reload listener successfully subscribed to 'policy:updated' channel")
        
        while True:
            try:
                # Polling message from pubsub subscription
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if message:
                    payload = message.get("data")
                    logger.info(f"Policy update event captured: '{payload}'. Invalidating permissions cache...")
                    # Invalidate and reload permissions
                    await load_permissions_to_cache()
            except Exception as loop_err:
                logger.error(f"Error handling pubsub message: {loop_err}")
                await asyncio.sleep(1)
                
            await asyncio.sleep(0.5)
            
    except asyncio.CancelledError:
        logger.info("Hot-reload listener background task cancelled")
    except Exception as e:
        logger.error(f"Failed to subscribe to policy updates: {e}")
        # Retry connection after a short delay
        await asyncio.sleep(5)
        asyncio.create_task(start_hot_reload_listener())
