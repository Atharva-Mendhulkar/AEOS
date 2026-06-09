"""Security helpers shared by AEOS FastAPI services."""

from __future__ import annotations

import json
import uuid
from collections.abc import Mapping, Sequence
from typing import Any

try:
    import bleach
except ImportError:  # pragma: no cover - dependency is declared; fallback keeps local imports usable.
    bleach = None


TEXT_KEYS = {
    "name",
    "policy_type",
    "created_by",
    "agent_identity",
    "action_description",
    "event_type",
    "context_type",
    "agent_type",
    "query_text",
    "error",
    "reason",
    "notes",
    "operator",
}


def sanitize_text(value: str) -> str:
    """Strip markup from user-controlled text while preserving plain content."""
    if bleach is None:
        return value.replace("<", "").replace(">", "")
    return bleach.clean(value, tags=[], attributes={}, protocols=[], strip=True)


def sanitize_json(value: Any) -> Any:
    """Recursively sanitize strings inside JSON-like data structures."""
    if isinstance(value, str):
        return sanitize_text(value)
    if isinstance(value, Mapping):
        return {sanitize_text(str(k)): sanitize_json(v) for k, v in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        return [sanitize_json(v) for v in value]
    return value


def sanitize_model_text_fields(model: Any) -> Any:
    """Return a copy of a Pydantic model with common text fields sanitized."""
    if not hasattr(model, "model_copy"):
        return model
    updates = {}
    for key in TEXT_KEYS:
        if hasattr(model, key):
            value = getattr(model, key)
            if isinstance(value, str):
                updates[key] = sanitize_text(value)
            elif isinstance(value, (dict, list)):
                updates[key] = sanitize_json(value)
    return model.model_copy(update=updates) if updates else model


def parse_json_config(config: str | dict[str, Any]) -> dict[str, Any]:
    """Parse and sanitize a JSON object policy config."""
    if isinstance(config, str):
        parsed = json.loads(config)
    else:
        parsed = config
    if not isinstance(parsed, dict):
        raise ValueError("Policy config must be a JSON object")
    return sanitize_json(parsed)


def validate_policy_config(policy_type: str, config: dict[str, Any]) -> None:
    """Validate governance policy configuration shape before persistence."""
    if policy_type == "permission":
        if not config.get("agent_type"):
            raise ValueError("Permission policy must specify 'agent_type'")
        permission_keys = ["allowed_resources", "denied_resources", "allowed_tools", "denied_tools"]
        if all(config.get(key) is None for key in permission_keys):
            raise ValueError(
                "Permission policy config must specify allowed_resources, denied_resources, "
                "allowed_tools, or denied_tools"
            )
        for key in permission_keys:
            value = config.get(key)
            if value is not None and not (
                isinstance(value, list) and all(isinstance(item, str) for item in value)
            ):
                raise ValueError(f"Permission key '{key}' must be a list of strings")
    elif policy_type == "anomaly":
        max_freq = config.get("max_frequency_per_minute")
        if max_freq is not None and (not isinstance(max_freq, (int, float)) or max_freq <= 0):
            raise ValueError("max_frequency_per_minute must be a positive number")
        max_consec = config.get("max_consecutive_identical_actions")
        if max_consec is not None and (not isinstance(max_consec, int) or max_consec <= 0):
            raise ValueError("max_consecutive_identical_actions must be a positive integer")
    elif policy_type == "risk_threshold":
        suspend_threshold = config.get("suspend_threshold")
        halt_threshold = config.get("halt_threshold")
        if suspend_threshold is not None and (
            not isinstance(suspend_threshold, (int, float)) or not 0.0 <= suspend_threshold <= 10.0
        ):
            raise ValueError("suspend_threshold must be a float between 0.0 and 10.0")
        if halt_threshold is not None and (
            not isinstance(halt_threshold, (int, float)) or not 0.0 <= halt_threshold <= 10.0
        ):
            raise ValueError("halt_threshold must be a float between 0.0 and 10.0")
        if suspend_threshold is not None and halt_threshold is not None and suspend_threshold > halt_threshold:
            raise ValueError("suspend_threshold cannot exceed halt_threshold")
    elif policy_type == "retention":
        days = config.get("retention_days")
        if days is None or not isinstance(days, int) or days <= 0:
            raise ValueError("retention_days must be a positive integer")
    else:
        raise ValueError(f"Unsupported policy_type: '{policy_type}'")


def add_security_middleware(app: Any) -> None:
    """Attach request ID and baseline security headers to a FastAPI app."""

    @app.middleware("http")
    async def security_headers(request, call_next):
        request_id = (
            request.headers.get("X-Request-ID")
            or request.headers.get("X-Correlation-ID")
            or str(uuid.uuid4())
        )
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Correlation-ID"] = request_id
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        return response
