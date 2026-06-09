"""Retention enforcement for partitioned audit and workflow-step data."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import asyncpg
from celery import Celery

logger = logging.getLogger("memory-agent.retention")

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/aeos")
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
RETENTION_DAYS = int(os.environ.get("AEOS_RETENTION_DAYS", "90"))

celery_app = Celery("memory_retention", broker=REDIS_URL, backend=REDIS_URL)
celery_app.conf.beat_schedule = {
    "memory-retention-daily": {
        "task": "memory.enforce_retention",
        "schedule": 24 * 60 * 60,
        "options": {"expires": 60 * 60},
    }
}
celery_app.conf.timezone = "UTC"

PARTITION_PARENTS = ("audit_trail", "workflow_steps")
IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
TO_BOUND_RE = re.compile(r"TO \('([^']+)'\)")


def _safe_identifier(name: str) -> str:
    if not IDENTIFIER_RE.match(name):
        raise ValueError(f"Unsafe partition identifier: {name}")
    return name


def _parse_upper_bound(bound_expression: str) -> datetime | None:
    match = TO_BOUND_RE.search(bound_expression)
    if not match:
        return None
    value = match.group(1).replace(" ", "T")
    return datetime.fromisoformat(value).astimezone(timezone.utc)


def _compute_audit_hash(row: dict[str, Any]) -> str:
    canonical = {}
    for key, value in row.items():
        if isinstance(value, datetime):
            canonical[key] = value.astimezone(timezone.utc).isoformat()
        elif isinstance(value, uuid.UUID):
            canonical[key] = str(value)
        elif isinstance(value, (dict, list)):
            canonical[key] = json.loads(json.dumps(value, sort_keys=True))
        elif isinstance(value, str) and (value.startswith("{") or value.startswith("[")):
            try:
                canonical[key] = json.loads(value)
            except Exception:
                canonical[key] = value
        elif isinstance(value, float):
            canonical[key] = round(value, 4)
        else:
            canonical[key] = value
    return hashlib.sha256(json.dumps(canonical, sort_keys=True).encode("utf-8")).hexdigest()


async def discover_expired_partitions(conn: asyncpg.Connection, cutoff: datetime) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        """
        SELECT parent.relname AS parent_name,
               child.relname AS partition_name,
               pg_get_expr(child.relpartbound, child.oid) AS partition_bound
        FROM pg_inherits
        JOIN pg_class child ON child.oid = pg_inherits.inhrelid
        JOIN pg_class parent ON parent.oid = pg_inherits.inhparent
        WHERE parent.relname = ANY($1::text[])
        ORDER BY parent.relname, child.relname
        """,
        list(PARTITION_PARENTS),
    )

    expired = []
    for row in rows:
        upper_bound = _parse_upper_bound(row["partition_bound"])
        if upper_bound and upper_bound < cutoff:
            expired.append(
                {
                    "parent_name": row["parent_name"],
                    "partition_name": row["partition_name"],
                    "upper_bound": upper_bound.isoformat(),
                }
            )
    return expired


async def _append_retention_audit(conn: asyncpg.Connection, dropped: list[dict[str, Any]], cutoff: datetime) -> None:
    prev_row = await conn.fetchrow(
        """
        SELECT event_type, timestamp, agent_identity, incident_id, workflow_id,
               action_description, inputs, outputs, risk_score, prev_entry_hash
        FROM audit_trail
        ORDER BY id DESC LIMIT 1
        """
    )
    if not prev_row:
        prev_entry_hash = "genesis"
    else:
        prev_entry_hash = _compute_audit_hash(dict(prev_row))

    await conn.execute(
        """
        INSERT INTO audit_trail (
            event_type, timestamp, agent_identity, action_description,
            inputs, outputs, prev_entry_hash, created_at
        ) VALUES ($1, NOW(), $2, $3, $4, $5, $6, NOW())
        """,
        "retention.enforced",
        "memory-agent",
        f"Retention job enforced 90-day partition policy; dropped {len(dropped)} partitions.",
        json.dumps({"cutoff": cutoff.isoformat(), "retention_days": RETENTION_DAYS}),
        json.dumps({"dropped_partitions": dropped}),
        prev_entry_hash,
    )


async def enforce_retention(
    database_url: str = DATABASE_URL,
    retention_days: int = RETENTION_DAYS,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Drop audit/workflow partitions older than the retention cutoff."""
    effective_now = now or datetime.now(timezone.utc)
    cutoff = effective_now - timedelta(days=retention_days)
    conn = await asyncpg.connect(database_url)
    dropped: list[dict[str, Any]] = []

    try:
        async with conn.transaction():
            expired = await discover_expired_partitions(conn, cutoff)
            for partition in expired:
                partition_name = _safe_identifier(partition["partition_name"])
                await conn.execute(f"DROP TABLE IF EXISTS {partition_name}")  # Partition name is validated above.
                dropped.append(partition)
            await _append_retention_audit(conn, dropped, cutoff)
    finally:
        await conn.close()

    logger.info("Retention enforcement complete: dropped %s partitions", len(dropped))
    return {
        "status": "enforced",
        "cutoff": cutoff.isoformat(),
        "retention_days": retention_days,
        "dropped_partitions": dropped,
    }


@celery_app.task(name="memory.enforce_retention")
def enforce_retention_task() -> dict[str, Any]:
    return asyncio.run(enforce_retention())
