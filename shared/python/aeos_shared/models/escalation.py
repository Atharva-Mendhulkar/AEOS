"""Escalation models for the Escalation Agent.

Covers escalation request and response structures.
Satisfies Requirements 5.5, 7.1–7.5.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from aeos_shared.models.incident import IncidentSeverity
from aeos_shared.models.workflow import ActionDescriptor


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class EscalationStatus(str, Enum):
    """Status of an escalation request."""

    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    timed_out = "timed_out"
    escalated = "escalated"


class EscalationTier(str, Enum):
    """Operator tier for escalation routing."""

    tier_1 = "tier_1"
    tier_2 = "tier_2"


class EscalationOption(str, Enum):
    """Available options for an escalation response."""

    approve = "approve"
    reject = "reject"
    modify = "modify"


# ---------------------------------------------------------------------------
# Escalation request
# ---------------------------------------------------------------------------


class EscalationRequest(BaseModel):
    """Structured escalation request sent to operators.

    Contains all required fields per Requirement 7.1:
    - incident_summary
    - proposed_action
    - risk_score
    - options (at minimum: approve, reject, modify)
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    incident_id: UUID
    workflow_id: UUID
    step_id: UUID
    incident_summary: str
    severity: IncidentSeverity | None = None
    proposed_action: ActionDescriptor
    risk_score: float = Field(ge=0.0, le=10.0)
    options: list[EscalationOption] = Field(
        default_factory=lambda: [
            EscalationOption.approve,
            EscalationOption.reject,
            EscalationOption.modify,
        ]
    )
    status: EscalationStatus = EscalationStatus.pending
    tier: EscalationTier = EscalationTier.tier_1
    created_at: datetime
    resolved_at: datetime | None = None
    resolved_by: str | None = None
    resolution_notes: str | None = None


# ---------------------------------------------------------------------------
# Escalation response
# ---------------------------------------------------------------------------


class EscalationResponse(BaseModel):
    """Response from an operator to an escalation request."""

    model_config = ConfigDict(from_attributes=True)

    escalation_id: UUID
    decision: EscalationOption
    modified_action: ActionDescriptor | None = None
    notes: str | None = None
    resolved_at: datetime


# ---------------------------------------------------------------------------
# Pending escalations query result
# ---------------------------------------------------------------------------


class PendingEscalation(BaseModel):
    """Summary of a pending escalation for listing endpoints."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    incident_id: UUID
    workflow_id: UUID
    step_id: UUID
    incident_summary: str
    risk_score: float
    status: EscalationStatus
    tier: EscalationTier
    created_at: datetime
    time_pending: datetime  # Computed as NOW() - created_at