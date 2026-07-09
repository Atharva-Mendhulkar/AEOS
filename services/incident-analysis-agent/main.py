from aeos_shared import get, post, put, delete
import os
import uuid
import json
import logging
import asyncio
from datetime import datetime, timezone
import httpx
from fastapi import FastAPI, HTTPException, status
import asyncpg
import redis.asyncio as aioredis
import google.generativeai as genai

from aeos_shared import (
    get,
    post,
    put,
    delete,

    AgentTask,
    AgentResult,
    AgentCapabilities,
    AgentHealthStatus,
    HealthStatus,
    AgentType,
    add_security_middleware,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("incident-analysis-agent")

COORDINATOR_URL = os.environ.get("COORDINATOR_URL", "http://coordinator:8001")
REDIS_URL = os.environ.get("REDIS_URL", "redis://:aeosredis@redis:6379/0")
CONFIDENCE_THRESHOLD = float(os.environ.get("CONFIDENCE_THRESHOLD", "0.7"))

app = FastAPI(title="Incident Analysis Agent", version="1.0.0")
add_security_middleware(app)
redis_conn = None
subscriber_task = None

async def process_classification(content: str) -> dict:
    """Classify incident content using Gemini Pro or mock if mock-key."""
    api_key = os.environ.get("GEMINI_API_KEY", "mock-key")
    model_name = os.environ.get("GEMINI_MODEL_ANALYSIS", "gemini-1.5-pro")
    
    # 1. Deterministic Mock Fallback for Integration Testing
    if api_key == "mock-key":
        content_lower = content.lower()
        if "critical" in content_lower:
            return {"severity": "critical", "confidence_score": 0.95, "root_signature": "CRITICAL_ALERT"}
        elif "error" in content_lower:
            return {"severity": "high", "confidence_score": 0.85, "root_signature": "SYSTEM_ERROR"}
        elif "warning" in content_lower:
            return {"severity": "medium", "confidence_score": 0.75, "root_signature": "SYSTEM_WARNING"}
        elif "low confidence" in content_lower or "ambiguous" in content_lower:
            return {"severity": "medium", "confidence_score": 0.50, "root_signature": "AMBIGUOUS_INPUT"}
        elif "info" in content_lower:
            return {"severity": "low", "confidence_score": 0.90, "root_signature": "SYSTEM_INFO"}
        else:
            return {"severity": "low", "confidence_score": 0.80, "root_signature": "GENERIC_INPUT"}

    # 2. Real Gemini Pro API Call
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(model_name)
        prompt = f"""
        You are the Incident Analysis Agent for AEOS.
        Classify the following operational input and determine:
        1. Severity level (critical, high, medium, low)
        2. Confidence score (0.0 to 1.0)
        3. Root signature (a concise unique string identifying the issue class, e.g. DATABASE_TIMEOUT)

        Input content:
        {content}

        Return ONLY a valid JSON object matching this schema:
        {{
          "severity": "critical" | "high" | "medium" | "low",
          "confidence_score": float,
          "root_signature": "string"
        }}
        Do not add any markdown formatting, backticks, or other text.
        """
        response = await model.generate_content_async(prompt)
        text = response.text.strip()
        # Clean markdown if generated
        if text.startswith("```json"):
            text = text[7:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
        
        return json.loads(text)
    except Exception as e:
        logger.error(f"Gemini API classification failed: {e}. Falling back to default.")
        return {"severity": "low", "confidence_score": 0.50, "root_signature": "FALLBACK_ERROR"}

async def process_and_report_task(task: AgentTask):
    logger.info(f"Processing task {task.task_id} for incident {task.incident_id}")
    
    # 1. Fetch input content from database
    db_url = os.environ.get("DATABASE_URL")
    content = ""
    try:
        conn = await asyncpg.connect(db_url)
        row = await conn.fetchrow(
            "SELECT format, raw_content, extracted_text, transcript FROM multimodal_inputs WHERE id = $1",
            task.incident_id
        )
        await conn.close()
        
        if row:
            content_parts = []
            if row["raw_content"]:
                content_parts.append(row["raw_content"])
            if row["extracted_text"]:
                content_parts.append(row["extracted_text"])
            if row["transcript"]:
                content_parts.append(row["transcript"])
            content = "\n\n".join(content_parts)
    except Exception as e:
        logger.error(f"Failed to fetch content from DB: {e}")
        # Report failure back to Coordinator
        await report_result(task, success=False, error=str(e))
        return

    # 2. Run classification
    res = await process_classification(content)
    
    # 3. Handle low-confidence
    severity = res.get("severity")
    confidence = res.get("confidence_score", 0.0)
    root_sig = res.get("root_signature", "UNKNOWN")
    requires_escalation = confidence < CONFIDENCE_THRESHOLD

    if requires_escalation:
        logger.info(f"Confidence score {confidence} below threshold {CONFIDENCE_THRESHOLD}. Escalation required.")
        severity = None

    output = {
        "severity": severity,
        "confidence_score": confidence,
        "root_signature": root_sig,
        "requires_escalation": requires_escalation
    }

    # 4. Report to Coordinator
    await report_result(task, success=True, output=output, requires_escalation=requires_escalation)

async def report_result(task: AgentTask, success: bool, output: dict = None, error: str = None, requires_escalation: bool = False):
    endpoint = f"{COORDINATOR_URL}/coordinator/step-complete" if success else f"{COORDINATOR_URL}/coordinator/step-failed"
    payload = {
        "task_id": str(task.task_id),
        "step_id": str(task.step_id),
        "workflow_id": str(task.workflow_id),
        "incident_id": str(task.incident_id),
        "success": success,
        "output": output,
        "error": error,
        "requires_escalation": requires_escalation
    }
    
    if True:
        try:
            logger.info(f"Reporting task result to Coordinator: {endpoint}")
            await post(endpoint, json=payload)
        except Exception as e:
            logger.error(f"Failed to report result to Coordinator: {e}")

async def redis_subscriber():
    global redis_conn
    while True:
        try:
            logger.info(f"Connecting to Redis at {REDIS_URL}...")
            redis_conn = aioredis.from_url(REDIS_URL)
            pubsub = redis_conn.pubsub()
            await pubsub.subscribe("agent:incident_analysis:tasks")
            logger.info("Successfully subscribed to agent:incident_analysis:tasks Redis channel")
            
            while True:
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if message:
                    data = message["data"]
                    try:
                        task_dict = json.loads(data)
                        task = AgentTask(**task_dict)
                        asyncio.create_task(process_and_report_task(task))
                    except Exception as parse_err:
                        logger.error(f"Failed to parse task JSON: {parse_err}")
                await asyncio.sleep(0.1)
        except Exception as e:
            logger.error(f"Redis connection / subscriber error: {e}. Reconnecting in 5s...")
            await asyncio.sleep(5)

@app.on_event("startup")
async def startup_event():
    global subscriber_task
    subscriber_task = asyncio.create_task(redis_subscriber())

@app.on_event("shutdown")
async def shutdown_event():
    global subscriber_task, redis_conn
    if subscriber_task:
        subscriber_task.cancel()
    if redis_conn:
        await redis_conn.close()

# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------
@app.get("/health")
async def health_check() -> HealthStatus:
    return HealthStatus(
        agent_type=AgentType.incident_analysis,
        status=AgentHealthStatus.healthy,
        message="Agent is healthy and listening to Redis",
        checked_at=datetime.now(timezone.utc)
    )

@app.get("/capabilities")
async def get_capabilities() -> AgentCapabilities:
    return AgentCapabilities(
        agent_type=AgentType.incident_analysis,
        supported_action_types=["classify"],
        max_concurrent_tasks=10
    )
