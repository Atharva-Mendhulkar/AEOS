"""Governance, policy, risk assessment, and validation models.

Covers the Runtime Governance Layer (L5) data structures.
Satisfies Requirements 5.1–5.7, 12.1–12.5.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class RiskLevel(str, Enum):
    """Risk classification derived from the computed risk score.

    Thresholds per design spec:
      - low:      0.0 – 6.9  → execute immediately
      - high:     7.0 – 8.9  → trigger Approval Gate
      - critical: 9.0 – 10.0 → activate Circuit Breaker
    """

    low = "low"
    high = "high"
    critical = "critical"


class GovernanceDecision(str, Enum):
    """Outcome of a Governance Layer validation request."""

    approved = "approved"
    suspended = "suspended"   # Approval Gate triggered; awaiting operator
    halted = "halted"         # Circuit Breaker activated; permanently stopped
    rejected = "rejected"     # Permission denied or policy violation


class PolicyType(str, Enum):
    """Governance policy categories stored in the ``policies`` table."""

    risk_threshold = "risk_threshold"
    permission = "permission"
    anomaly = "anomaly"
    retention = "retention"


class ScoringMethod(str, Enum):
    """Method used to compute the risk score for an action."""

    rule_based = "rule_based"
    llm = "llm"


# ---------------------------------------------------------------------------
# Risk assessment
# ---------------------------------------------------------------------------


class RiskAssessment(BaseModel):
    """Risk score and contributing factors for a proposed action.

    Produced by the risk scoring engine (rule-based or LLM-based).
    Satisfies Requirement 5.1.
    """

    model_config = ConfigDict(from_attributes=True)

    score: float = Field(ge=0.0, le=10.0)
    factors: list[str] = Field(default_factory=list)
    scoring_method: ScoringMethod


# ---------------------------------------------------------------------------
# Policy violation
# ---------------------------------------------------------------------------


class PolicyViolation(BaseModel):
    """Describes a single policy constraint violated by a proposed action or plan.

    Returned by POST /governance/validate-plan when the plan is rejected.
    Satisfies Requirements 3.3, 5.4.
    """

    model_config = ConfigDict(from_attributes=True)

    policy_id: UUID
    policy_name: str
    violation_type: str
    description: str
    step_id: UUID | None = None


# ---------------------------------------------------------------------------
# Governance result
# ---------------------------------------------------------------------------


class GovernanceResult(BaseModel):
    """Full result of a Governance Layer validation call.

    Returned by POST /governance/validate-action and
    POST /governance/validate-plan.
    """

    model_config = ConfigDict(from_attributes=True)

    decision: GovernanceDecision
    risk_assessment: RiskAssessment | None = None
    violations: list[PolicyViolation] = Field(default_factory=list)
    escalation_id: UUID | None = None
    reason: str | None = None


# ---------------------------------------------------------------------------
# Validation result (plan-level)
# ---------------------------------------------------------------------------


class ValidationResult(BaseModel):
    """Result of validating an execution plan against governance policies.

    Returned by the Planner's internal DAG check and by the Governance Layer's
    plan validation endpoint.  Satisfies Requirements 3.3, 3.4.
    """

    model_config = ConfigDict(from_attributes=True)

    is_valid: bool
    violations: list[PolicyViolation] = Field(default_factory=list)
    reason: str | None = None


# ---------------------------------------------------------------------------
# Policy
# ---------------------------------------------------------------------------


class Policy(BaseModel):
    """A governance policy record stored in the ``policies`` table.

    Supports hot-reload: when updated, the Governance Layer reloads within
    10 seconds (Requirement 12.3).
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    version: int = Field(default=1, ge=1)
    is_active: bool = True
    policy_type: PolicyType
    config: dict
    created_by: str
    created_at: datetime
    updated_at: datetime
