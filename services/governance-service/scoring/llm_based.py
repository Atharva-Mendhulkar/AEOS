import os
import json
import hashlib
import logging
from typing import Dict, Any, Optional
import redis.asyncio as redis
from pydantic import BaseModel
from scoring.rule_based import RiskAssessment

logger = logging.getLogger("governance-scoring-llm")

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "mock-key")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL_GOVERNANCE", "gemini-1.5-pro")

# Lazy Redis client setup
redis_client = None

def get_redis_client():
    global redis_client
    if redis_client is None:
        redis_client = redis.from_url(REDIS_URL, decode_responses=True)
    return redis_client

def get_action_hash(action: Dict[str, Any]) -> str:
    """Deterministic JSON serialization hash of the action."""
    action_str = json.dumps(action, sort_keys=True)
    return hashlib.sha256(action_str.encode('utf-8')).hexdigest()

async def evaluate_llm_risk(action: Dict[str, Any], agent_type: str, policy_context: Optional[str] = None) -> RiskAssessment:
    # 1. Try to fetch from Redis cache
    action_hash = get_action_hash(action)
    cache_key = f"governance:risk_cache:{action_hash}"
    
    r = get_redis_client()
    try:
        cached_val = await r.get(cache_key)
        if cached_val:
            logger.info("Governance LLM risk score cache hit")
            data = json.loads(cached_val)
            return RiskAssessment(
                score=data["score"],
                factors=data["factors"],
                scoring_method="llm"
            )
    except Exception as re:
        logger.warning(f"Failed to query Redis cache: {re}")

    # 2. Cache miss: evaluate using Gemini or mock
    score = 5.0
    factors = ["LLM assessment"]
    
    if GEMINI_API_KEY == "mock-key":
        logger.info("Using mock LLM risk scoring")
        # Deterministic mock calculation based on tool name/params if mock
        tool = action.get("tool", "")
        if "critical" in tool or "database" in tool:
            score = 9.2
            factors = ["Mock LLM: Database modification detected", "High priority path risk"]
        elif "remediate" in tool:
            score = 6.5
            factors = ["Mock LLM: Routine remediation action"]
        else:
            score = 5.5
            factors = ["Mock LLM: General agent utility task"]
    else:
        # Call Gemini Pro
        import google.generativeai as genai
        try:
            genai.configure(api_key=GEMINI_API_KEY)
            model = genai.GenerativeModel(GEMINI_MODEL)
            
            prompt = f"""
            You are the Governance Agent for AEOS.
            Assess the runtime risk of the following operational action:
            Agent: {agent_type}
            Action: {json.dumps(action, indent=2)}
            Policy Context: {policy_context or 'None'}
            
            Provide a risk score from 0.0 (no risk) to 10.0 (extreme risk/harm) and list key risk factors.
            Return ONLY a valid JSON object matching this schema:
            {{
              "score": float,
              "factors": ["factor 1", "factor 2"]
            }}
            Do not wrap with markdown formatting or other text.
            """
            response = await model.generate_content_async(prompt)
            text = response.text.strip()
            if text.startswith("```json"):
                text = text[7:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()
            
            result = json.loads(text)
            score = max(0.0, min(10.0, float(result.get("score", 5.0))))
            factors = result.get("factors", ["LLM evaluated score"])
        except Exception as e:
            logger.error(f"Gemini risk scoring failed: {e}. Defaulting to standard risk.")
            score = 7.0
            factors = [f"LLM fallback evaluation due to error: {e}"]

    assessment = RiskAssessment(
        score=score,
        factors=factors,
        scoring_method="llm"
    )

    # 3. Cache the result in Redis with 5-minute TTL
    try:
        await r.setex(
            cache_key,
            300, # 5 minutes
            json.dumps({"score": score, "factors": factors})
        )
    except Exception as re:
        logger.warning(f"Failed to cache risk assessment: {re}")

    return assessment
