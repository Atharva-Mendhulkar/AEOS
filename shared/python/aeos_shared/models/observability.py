"""Observability Layer data models: WebSocket events and execution traces.

Covers the Observability Layer data structures.
Satisfies Requirements 8.1–8.7.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from aeos_shared.models.workflow import AgentType


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class WebSocketEventType(str, Enum):
    """All WebSocket event type literals emitted by the Observability Layer.

    Matches the event table in the design spec.
    Satisfies Requirement 8.2.
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


class AgentState(str, Enum):
    """Operational state of a Specialist Agent instance."""

    active = "active"
    idle = "idle"
    blocked = "blocked"


class WorkflowOutcome(str, Enum):
    """Terminal outcome of a completed workflow."""

    success = "success"
    partial_failure = "partial_failure"
    failed = "failed"


class FailureType(str, Enum):
    """Classification of a step failure by the Recovery Agent."""

    transient = "transient"
    permanent = "permanent"


# ---------------------------------------------------------------------------
# WebSocket event model
# ---------------------------------------------------------------------------


class WebSocketEvent(BaseModel):
    """A single event emitted to the WebSocket stream.

    The ``sequence`` field is a monotonically increasing integer used by
    reconnecting clients to request replay of missed events (Requirement 8.2).
    """

    model_config = ConfigDict(from_attributes=True)

    type: WebSocketEventType
    sequence: int = Field(ge=0)
    payload: dict
    emitted_at: datetime


# ---------------------------------------------------------------------------
# Execution trace
# ---------------------------------------------------------------------------


class TraceEntry(BaseModel):
    """A single entry in an execution trace timeline."""

    model_config = ConfigDict(from_attributes=True)

    event_type: str
    agent_type: AgentType | None = None
    step_id: UUID | None = None
    timestamp: datetime
    details: dict = Field(default_factory=dict)


class ExecutionTrace(BaseModel):
    """Complete execution trace for a single workflow run.

    Captures all agent invocations, tool calls, state transitions, inputs,
    outputs, and timestamps (Requirement 8.1).  Retained for a minimum of
    90 days (Requirement 8.6).
    """

    model_config = ConfigDict(from_attributes=True)

    workflow_id: UUID
    incident_id: UUID
    entries: list[TraceEntry] = Field(default_factory=list)
    started_at: datetime
    completed_at: datetime | None = None
    outcome: WorkflowOutcome | None = None
