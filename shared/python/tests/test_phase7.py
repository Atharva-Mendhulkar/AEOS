import os
import sys
from datetime import datetime, timezone

import pytest

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
sys.path.insert(0, os.path.join(BASE_DIR, "shared/python"))
sys.path.insert(0, os.path.join(BASE_DIR, "services/memory-agent"))

from aeos_shared.security import parse_json_config, sanitize_json, sanitize_text, validate_policy_config
from main import compute_entry_hash
from memory_jobs.retention import _compute_audit_hash, _parse_upper_bound, _safe_identifier


def test_sanitize_text_strips_markup():
    assert sanitize_text("<script>alert(1)</script>Critical") == "alert(1)Critical"


def test_sanitize_json_recurses_nested_payloads():
    payload = {"name": "<b>policy</b>", "items": ["<i>tool</i>"]}
    assert sanitize_json(payload) == {"name": "policy", "items": ["tool"]}


def test_policy_config_validation_accepts_known_policy_types():
    configs = [
        ("permission", {"agent_type": "operations", "allowed_tools": ["gather_logs"]}),
        ("anomaly", {"max_frequency_per_minute": 10, "max_consecutive_identical_actions": 3}),
        ("risk_threshold", {"suspend_threshold": 7.0, "halt_threshold": 9.0}),
        ("retention", {"retention_days": 90}),
    ]
    for policy_type, config in configs:
        validate_policy_config(policy_type, config)


def test_policy_config_validation_rejects_invalid_jsonb_shape():
    with pytest.raises(ValueError):
        validate_policy_config("permission", {"allowed_tools": ["gather_logs"]})
    with pytest.raises(ValueError):
        validate_policy_config("risk_threshold", {"suspend_threshold": 9.5, "halt_threshold": 8.0})
    with pytest.raises(ValueError):
        validate_policy_config("retention", {"retention_days": 0})


def test_parse_json_config_requires_object():
    assert parse_json_config('{"retention_days":90}') == {"retention_days": 90}
    with pytest.raises(ValueError):
        parse_json_config("[1,2,3]")


def test_retention_partition_bound_parsing_and_identifier_safety():
    bound = "FOR VALUES FROM ('2026-01-01 00:00:00+00') TO ('2026-02-01 00:00:00+00')"
    assert _parse_upper_bound(bound) == datetime(2026, 2, 1, tzinfo=timezone.utc)
    assert _safe_identifier("audit_trail_y2026m01") == "audit_trail_y2026m01"
    with pytest.raises(ValueError):
        _safe_identifier("audit_trail_y2026m01; DROP TABLE audit_trail")


def test_retention_audit_hash_normalizes_jsonb_strings():
    row = {
        "event_type": "step.completed",
        "timestamp": datetime(2026, 6, 9, tzinfo=timezone.utc),
        "agent_identity": "operations",
        "incident_id": None,
        "workflow_id": None,
        "action_description": "done",
        "inputs": {"service": "db"},
        "outputs": ["ok"],
        "risk_score": 1.23456,
        "prev_entry_hash": "genesis",
    }
    jsonb_as_strings = {
        **row,
        "inputs": '{"service":"db"}',
        "outputs": '["ok"]',
    }

    assert _compute_audit_hash(row) == _compute_audit_hash(jsonb_as_strings)
    assert compute_entry_hash(row) == compute_entry_hash(jsonb_as_strings)
