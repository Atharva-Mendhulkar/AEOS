"""Agent task, result, capability, and permission models.

Mirrors the L4 Specialist Agent Layer interface from the design spec.
Satisfies Requirements 4.1, 4.3, 5.4.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from aeos_shared.models.workflow import ActionDescriptor, AgentType


# ---------------------------------------------------------------------------
# Permission and context models
# ---------------------------------------------------------------------------


class PermissionScope(BaseModel):
    """Defines the resource and API scope granted to a Specialist Agent.

    Loaded from governance policies at startup and enforced by the
    Governance Layer before every action execution (Requirement 5.4).
    """

    model_config = ConfigDict(from_attributes=True)

    agent_type: AgentType
    allowed_resources: list[str] = Field(default_factory=list)
    denied_resources: list[str] = Field(default_factory=list)
    allowed_api_scopes: list[str] = Field(default_factory=list)


class OperationalContext(BaseModel):
    """Historical context retrieved from the Memory Agent for agent reasoning.

    Passed to each Specialist Agent alongside its task so it can reason
    with historical incident resolutions, agent metrics, and policy constraints.
    """

    model_config = ConfigDict(from_attributes=True)

    incident_id: UUID | None = None
    historical_resolutions: list[dict] = Field(default_factory=list)
    agent_metrics: dict = Field(default_factory=dict)
    policy_constraints: dict = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Task and result models
# ---------------------------------------------------------------------------


class AgentTask(BaseModel):
    """Task dispatched by the Coordinator to a Specialist Agent via Redis pub-sub.

    Mirrors the AgentTask class in the design spec (L4 Specialist Agent Layer).
    Satisfies Requirement 4.1.
    """

    model_config = ConfigDict(from_attributes=True)

    task_id: UUID
    workflow_id: UUID
    step_id: UUID
    incident_id: UUID
    action: ActionDescriptor
    context: OperationalContext
    permissions: PermissionScope


class AgentResult(BaseModel):
    """Result returned by a Specialist Agent after processing a task.

    Reported back to the Coordinator via POST /coordinator/step-complete
    or POST /coordinator/step-failed.
    """

    model_config = ConfigDict(from_attributes=True)

    task_id: UUID
    step_id: UUID
    workflow_id: UUID
    success: bool
    output: dict | None = None
    error: str | None = None
    requires_escalation: bool = False


# ---------------------------------------------------------------------------
# Health and capability models
# ---------------------------------------------------------------------------


class AgentHealthStatus(str, Enum):
    """Operational health states for a Specialist Agent."""

    healthy = "healthy"
    degraded = "degraded"
    unhealthy = "unhealthy"


class HealthStatus(BaseModel):
    """Health check response returned by each Specialist Agent service.

    Exposed via GET /health on every agent FastAPI service.
    """

    model_config = ConfigDict(from_attributes=True)

    agent_type: AgentType
    status: AgentHealthStatus
    message: str | None = None
    checked_at: datetime


class AgentCapabilities(BaseModel):
    """Capabilities advertised by a Specialist Agent.

    Returned by GET /capabilities on each agent service so the Coordinator
    can make informed routing decisions.
    """

    model_config = ConfigDict(from_attributes=True)

    agent_type: AgentType
    supported_action_types: list[str] = Field(default_factory=list)
    max_concurrent_tasks: int = Field(default=1, ge=1)
