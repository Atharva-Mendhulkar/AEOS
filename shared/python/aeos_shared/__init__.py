"""
AEOS Shared Python Package

Provides Pydantic v2 data models and authentication utilities
shared across all AEOS FastAPI services.
"""

from aeos_shared.auth.jwt_auth import (
    JWTPayload,
    RBAC_PERMISSIONS,
    verify_jwt,
    require_auth,
    require_role,
)
from aeos_shared.models.incident import (
    MultimodalInputFormat,
    MultimodalInputStatus,
    IncidentSeverity,
    IncidentStatus,
    MultimodalInput,
    Incident,
    ClassificationResult,
)
from aeos_shared.models.workflow import (
    WorkflowStatus,
    StepStatus,
    AgentType,
    ActionDescriptor,
    WorkflowStep,
    ExecutionPlan,
    Workflow,
)
from aeos_shared.models.agent import (
    PermissionScope,
    OperationalContext,
    AgentTask,
    AgentResult,
    HealthStatus,
    AgentCapabilities,
    AgentHealthStatus,
)
from aeos_shared.models.governance import (
    RiskLevel,
    GovernanceDecision,
    PolicyType,
    PolicyViolation,
    RiskAssessment,
    GovernanceResult,
    ValidationResult,
    Policy,
)
from aeos_shared.models.memory import (
    AuditEventType,
    AuditTrailEntry,
    ContextType,
    OperationalContextRecord,
)
from aeos_shared.models.observability import (
    WebSocketEventType,
    WebSocketEvent,
    AgentState,
    ExecutionTrace,
    TraceEntry,
    WorkflowOutcome,
    FailureType,
)
from aeos_shared.models.escalation import (
    EscalationStatus,
    EscalationTier,
    EscalationOption,
    EscalationRequest,
    EscalationResponse,
    PendingEscalation,
)
from aeos_shared.db import (
    get_db,
    init_db_pool,
    close_db_pool,
)

__all__ = [
    # auth
    "JWTPayload",
    "RBAC_PERMISSIONS",
    "verify_jwt",
    "require_auth",
    "require_role",
    # incident
    "MultimodalInputFormat",
    "MultimodalInputStatus",
    "IncidentSeverity",
    "IncidentStatus",
    "MultimodalInput",
    "Incident",
    "ClassificationResult",
    # workflow
    "WorkflowStatus",
    "StepStatus",
    "AgentType",
    "ActionDescriptor",
    "WorkflowStep",
    "ExecutionPlan",
    "Workflow",
    # agent
    "PermissionScope",
    "OperationalContext",
    "AgentTask",
    "AgentResult",
    "HealthStatus",
    "AgentCapabilities",
    "AgentHealthStatus",
    # governance
    "RiskLevel",
    "GovernanceDecision",
    "PolicyType",
    "PolicyViolation",
    "RiskAssessment",
    "GovernanceResult",
    "ValidationResult",
    "Policy",
    # memory
    "AuditEventType",
    "AuditTrailEntry",
    "ContextType",
    "OperationalContextRecord",
    # observability
    "WebSocketEventType",
    "WebSocketEvent",
    "AgentState",
    "ExecutionTrace",
    "TraceEntry",
    "WorkflowOutcome",
    "FailureType",
    # escalation
    "EscalationStatus",
    "EscalationTier",
    "EscalationOption",
    "EscalationRequest",
    "EscalationResponse",
    "PendingEscalation",
    # db
    "get_db",
    "init_db_pool",
    "close_db_pool",
]
