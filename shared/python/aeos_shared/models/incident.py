"""Incident and multimodal input data models."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class MultimodalInputFormat(str, Enum):
    """Supported multimodal input formats."""

    text = "text"
    json = "json"
    pdf = "pdf"
    image = "image"
    log = "log"
    audio = "audio"
    transcript = "transcript"


class MultimodalInputStatus(str, Enum):
    """Processing status for multimodal inputs."""

    pending = "pending"
    processing = "processing"
    ready = "ready"
    failed = "failed"


class IncidentSeverity(str, Enum):
    """Incident severity levels."""

    critical = "critical"
    high = "high"
    medium = "medium"
    low = "low"


class IncidentStatus(str, Enum):
    """Incident lifecycle status."""

    open = "open"
    in_progress = "in_progress"
    resolved = "resolved"
    escalated = "escalated"


class MultimodalInput(BaseModel):
    """Represents a multimodal input submitted for incident processing."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    format: MultimodalInputFormat
    file_path: str | None = None
    raw_content: str | None = None
    extracted_text: str | None = None
    transcript: str | None = None
    file_size_bytes: int | None = None
    processing_status: MultimodalInputStatus
    created_at: datetime


class Incident(BaseModel):
    """Represents a classified operational incident."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    root_signature: str
    severity: IncidentSeverity | None = None
    confidence_score: float | None = Field(default=None, ge=0.0, le=1.0)
    status: IncidentStatus
    source_input_ref: UUID | None = None
    workflow_id: UUID | None = None
    created_at: datetime
    updated_at: datetime


class ClassificationResult(BaseModel):
    """Result of incident classification by the Incident Analysis Agent."""

    model_config = ConfigDict(from_attributes=True)

    severity: IncidentSeverity | None = None
    confidence_score: float = Field(ge=0.0, le=1.0)
    root_signature: str
    requires_escalation: bool
