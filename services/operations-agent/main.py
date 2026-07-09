import os
import json
import logging
import asyncio
from typing import Dict, Any, Optional

from fastapi import FastAPI
import httpx
import redis.asyncio as redis
from aeos_shared import add_security_middleware

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("operations-agent")

app = FastAPI(title="Operations Agent", version="1.0.0")
add_security_middleware(app)

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
COORDINATOR_URL = os.environ.get("COORDINATOR_URL", "http://coordinator:8001")
AGENT_TYPE = "operations"

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(listen_to_tasks())
    logger.info("Operations Agent subscriber loop started.")

should_stop = False

async def listen_to_tasks():
    logger.info(f"Subscribing to agent:{AGENT_TYPE}:tasks channel...")
    r_client = redis.from_url(REDIS_URL, decode_responses=True)
    pubsub = r_client.pubsub()
    await pubsub.subscribe(f"agent:{AGENT_TYPE}:tasks")
    
    while not should_stop:
        try:
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if message:
                data = json.loads(message["data"])
                asyncio.create_task(process_task(data))
        except Exception as e:
            if not should_stop:
                logger.error(f"Error in task listener loop: {e}")
                await asyncio.sleep(1.0)
    
    await pubsub.unsubscribe(f"agent:{AGENT_TYPE}:tasks")
    await r_client.close()

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
            
        # Mock operations actions
        if tool == "restart_service":
            output = {"status": "success", "service": params.get("service_name", "unknown"), "restarted": True}
        elif tool == "gather_logs":
            output = {"status": "success", "service": params.get("service", "unknown"), "logs": "No errors found"}
        else:
            output = {"status": "success", "executed": tool}
            
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
    uvicorn.run(app, host="0.0.0.0", port=8012)
