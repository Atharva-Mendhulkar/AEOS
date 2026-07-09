from aeos_shared import create_graceful_lifespan
from prometheus_fastapi_instrumentator import Instrumentator
from aeos_shared import get, post, put, delete
import os
import json
import logging
import asyncio
from typing import Dict, Any, Optional

from fastapi import FastAPI
import httpx
import redis.asyncio as redis
from aeos_shared.kafka_client import KafkaPubSub
from aeos_shared import add_security_middleware

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("validation-agent")

app = FastAPI(title="Validation Agent", version="1.0.0")

# Expose Prometheus metrics
Instrumentator().instrument(app).expose(app)

add_security_middleware(app)

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
KAFKA_URL = os.environ.get("KAFKA_URL", "kafka:29092")
COORDINATOR_URL = os.environ.get("COORDINATOR_URL", "http://coordinator:8001")
AGENT_TYPE = "validation"


async def startup_event():
    asyncio.create_task(listen_to_tasks())
    logger.info("Validation Agent subscriber loop started.")

should_stop = False

kafka_pubsub = KafkaPubSub(KAFKA_URL)

async def listen_to_tasks():
    logger.info(f"Subscribing to agent_{AGENT_TYPE}_tasks topic...")
    try:
        await kafka_pubsub.subscribe(f"agent_{AGENT_TYPE}_tasks", f"{AGENT_TYPE}_group", process_task)
    except asyncio.CancelledError:
        logger.info("Task listener cancelled.")
    except Exception as e:
        logger.error(f"Error in task listener loop: {e}")

async def process_task(task_data: dict):
    task_id = task_data.get("task_id")
    workflow_id = task_data.get("workflow_id")
    step_id = task_data.get("step_id")
    incident_id = task_data.get("incident_id")
    action = task_data.get("action") or {}
    
    tool = action.get("tool", "unknown")
    params = action.get("params", {})
    
    logger.info(f"Processing task {task_id} for step {step_id} (tool: {tool})")
    
    try:
        if params.get("fail", False):
            raise ValueError(f"Simulated execution failure for tool {tool}")
            
        # Mock validation actions
        output = {"status": "success", "validation_passed": True}
            
        if True:
            await post(
                f"{COORDINATOR_URL}/coordinator/step-complete",
                json={
                    "task_id": task_id,
                    "step_id": step_id,
                    "workflow_id": workflow_id,
                    "output": output,
                    "requires_escalation": False
                },
                timeout=5.0
            )
            logger.info(f"Successfully posted step-complete callback for {step_id}")
    except Exception as e:
        logger.error(f"Failed to execute task {task_id}: {e}")
        if True:
            try:
                await post(
                    f"{COORDINATOR_URL}/coordinator/step-failed",
                    json={
                        "task_id": task_id,
                        "step_id": step_id,
                        "workflow_id": workflow_id,
                        "incident_id": incident_id,
                        "error": str(e)
                    },
                    timeout=5.0
                )
                logger.info(f"Successfully posted step-failed callback for {step_id}")
            except Exception as ce:
                logger.error(f"Failed to send step-failed callback: {ce}")

@app.get("/health")
async def health():
    return {"status": "healthy", "service": AGENT_TYPE}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8014)


# Inject Graceful Lifespan
app.router.lifespan_context = create_graceful_lifespan(
    startup_func=startup_event,
    shutdown_func=None
)
