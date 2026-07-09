import os
import json
import asyncio
import logging
import logging
from aeos_shared.kafka_client import KafkaPubSub
from permissions.enforcer import load_permissions_to_cache

logger = logging.getLogger("governance-hot-reload")
KAFKA_URL = os.environ.get("KAFKA_URL", "kafka:29092")
kafka_pubsub = KafkaPubSub(KAFKA_URL)

async def process_policy_update(payload: dict):
    logger.info(f"Policy update event captured: '{payload}'. Invalidating permissions cache...")
    # Invalidate and reload permissions
    await load_permissions_to_cache()

async def start_hot_reload_listener():
    """Subscribes to Kafka to receive real-time policy reload triggers."""
    try:
        logger.info("Governance hot-reload listener subscribing to 'policy_updated' topic")
        await kafka_pubsub.subscribe("policy_updated", "governance_group", process_policy_update)
    except asyncio.CancelledError:
        logger.info("Hot-reload listener background task cancelled")
    except Exception as e:
        logger.error(f"Failed to subscribe to policy updates: {e}")
        # Retry connection after a short delay
        await asyncio.sleep(5)
        asyncio.create_task(start_hot_reload_listener())
