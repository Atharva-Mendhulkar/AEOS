from typing import Dict, Any, List
from pydantic import BaseModel, Field

class RiskAssessment(BaseModel):
    score: float = Field(..., ge=0.0, le=10.0)
    factors: List[str] = Field(default_factory=list)
    scoring_method: str = "rule_based"

def evaluate_rule_based_risk(action: Dict[str, Any]) -> RiskAssessment:
    tool = action.get("tool", "")
    params = action.get("params", {})
    
    # 1. Determine action type and base score
    # Check explicit parameter override first
    action_type = params.get("action_type")
    
    if not action_type:
        # Infer from tool name/characteristics
        tool_lower = tool.lower()
        if any(kw in tool_lower for kw in ["write", "insert", "update", "delete", "db_write", "alter", "drop"]):
            action_type = "database write"
        elif any(kw in tool_lower for kw in ["file", "dir", "path", "upload", "download"]):
            action_type = "file operations"
        elif any(kw in tool_lower for kw in ["api", "http", "call", "request", "webhook"]):
            action_type = "API calls to known endpoints"
        elif any(kw in tool_lower for kw in ["read", "get", "query", "select", "gather", "verify", "health"]):
            action_type = "read-only queries"
        else:
            action_type = "unknown"

    # Base scores matching spec
    base_scores = {
        "database write": 6.0,
        "file operations": 5.0,
        "API calls to known endpoints": 4.0,
        "read-only queries": 2.0,
        "unknown": 5.0
    }
    
    base_score = base_scores.get(action_type, 5.0)
    factors = [f"Base risk for {action_type}: {base_score}"]
    score = base_score
    
    # 2. Modifiers
    # Modifier: Production vs Staging scope (+2.0)
    scope = params.get("scope", "staging")
    if scope == "production":
        score += 2.0
        factors.append("Production scope modifier: +2.0")
        
    # Modifier: Data sensitivity (+1.5)
    sensitivity = params.get("data_sensitivity")
    if sensitivity is True or sensitivity == "high" or sensitivity == "sensitive":
        score += 1.5
        factors.append("Data sensitivity modifier: +1.5")
        
    # Modifier: Irreversibility (+1.0)
    irreversible = params.get("irreversible") or params.get("irreversibility")
    if irreversible is True or irreversible == "high":
        score += 1.0
        factors.append("Irreversibility modifier: +1.0")
        
    # Cap score between 0.0 and 10.0
    score = max(0.0, min(10.0, score))
    
    return RiskAssessment(
        score=score,
        factors=factors,
        scoring_method="rule_based"
    )
