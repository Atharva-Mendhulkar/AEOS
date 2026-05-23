"""Workflow, step, and execution plan data models."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class WorkflowStatus(str, Enum):
    """Workflow lifecycle status."""

    planning = "planning"
    executing = "executing"
    suspended = "suspended"
    completed = "completed"
    failed = "failed"


class StepStatus(str, Enum):
    """Individual workflow step status."""

    pending = "pending"
    active = "active"
    completed = "completed"
    failed = "failed"
    suspended = "suspended"


class AgentType(str, Enum):
    """Specialist agent types in the AEOS system."""

    planner = "planner"
    incident_analysis = "incident_analysis"
    operations = "operations"
    compliance = "compliance"
    validation = "validation"
    recovery = "recovery"
    escalation = "escalation"
    memory = "memory"


class ActionDescriptor(BaseModel):
    """Describes a discrete action to be executed by an agent."""

    model_config = ConfigDict(from_attributes=True)

    tool: str
    params: dict
    timeout_seconds: int = Field(default=30)


class WorkflowStep(BaseModel):
    """A single step within a workflow execution plan."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workflow_id: UUID
    agent_type: AgentType
    action: ActionDescriptor
    status: StepStatus
    depends_on: list[UUID] = Field(default_factory=list)
    risk_score: float | None = Field(default=None, ge=0.0, le=10.0)
    output: dict | None = None
    retry_count: int = Field(default=0)
    created_at: datetime
    updated_at: datetime


class ExecutionPlan(BaseModel):
    """A complete execution plan composed of ordered, dependency-linked steps."""

    model_config = ConfigDict(from_attributes=True)

    steps: list[WorkflowStep]
    metadata: dict = Field(default_factory=dict)


class Workflow(BaseModel):
    """Represents a workflow orchestrating the resolution of an incident."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    incident_id: UUID
    plan: ExecutionPlan | None = None
    status: WorkflowStatus
    current_step_ids: list[UUID] = Field(default_factory=list)
    retry_count: int = Field(default=0)
    checkpoint: dict | None = None
    created_at: datetime
    updated_at: datetime
