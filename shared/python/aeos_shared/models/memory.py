"""Memory Agent data models: audit trail and operational context.

Covers the L7 Persistence Layer data structures.
Satisfies Requirements 8.5, 8.6, 10.1–10.5.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class AuditEventType(str, Enum):
    """Well-known event types recorded in the audit trail.

    Services may emit additional event types as free-form strings; this enum
    covers the events defined in the design spec WebSocket event table.
    """

    incident_classified = "incident.classified"
    step_started = "step.started"
    step_completed = "step.completed"
    step_failed = "step.failed"
    escalation_triggered = "escalation.triggered"
    escalation_resolved = "escalation.resolved"
    circuit_breaker_activated = "circuit_breaker.activated"
    workflow_completed = "workflow.completed"
    anomaly_detected = "anomaly.detected"
    policy_updated = "policy.updated"
    agent_state_changed = "agent.state_changed"
    governance_approved = "governance.approved"
    governance_rejected = "governance.rejected"
    governance_suspended = "governance.suspended"
    governance_halted = "governance.halted"
    recovery_invoked = "recovery.invoked"
    retry_attempted = "retry.attempted"
    preprocessing_completed = "preprocessing.completed"
    workflow_restored = "workflow.restored"
    format_rejected = "format.rejected"


class ContextType(str, Enum):
    """Categories of long-term operational context stored by the Memory Agent.

    Matches the CHECK constraint on ``operational_context.context_type``.
    """

    incident_resolution = "incident_resolution"
    agent_metric = "agent_metric"
    policy_decision = "policy_decision"


# ---------------------------------------------------------------------------
# Audit trail
# ---------------------------------------------------------------------------


class AuditTrailEntry(BaseModel):
    """An immutable, hash-chained audit trail record.

    Each entry stores the SHA-256 hash of the canonical JSON of the previous
    entry, making tampering detectable (Requirement 8.5).  The first entry
    uses ``prev_entry_hash = "genesis"``.

    The ``id`` field is a BIGINT GENERATED ALWAYS AS IDENTITY in PostgreSQL;
    it is optional here to allow construction before persistence.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int | None = None
    event_type: str
    timestamp: datetime
    agent_identity: str
    incident_id: UUID | None = None
    workflow_id: UUID | None = None
    action_description: str
    inputs: dict | None = None
    outputs: dict | None = None
    risk_score: float | None = Field(default=None, ge=0.0, le=10.0)
    prev_entry_hash: str


# ---------------------------------------------------------------------------
# Operational context (long-term memory)
# ---------------------------------------------------------------------------


class OperationalContextRecord(BaseModel):
    """A long-term memory record stored in the ``operational_context`` table.

    Used by Specialist Agents to retrieve historical incident resolutions,
    agent performance metrics, and policy decisions during planning and
    execution (Requirements 10.3, 10.4).

    The ``embedding_vector`` field holds a 1536-dimensional pgvector embedding
    for semantic similarity search; it is omitted from most API responses.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    context_type: ContextType
    incident_id: UUID | None = None
    agent_type: str | None = None
    content: dict
    embedding_vector: list[float] | None = Field(default=None, min_length=1536, max_length=1536)
    created_at: datetime
