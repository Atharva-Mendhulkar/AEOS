-- =============================================================================
-- AEOS Control Panel — Initial Schema Migration
-- Migration: 001_initial_schema.sql
-- Requirements: 8.5, 8.6, 10.1
-- =============================================================================

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "pgcrypto";   -- gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS "vector";     -- pgvector for semantic search (operational_context.embedding_vector)

-- =============================================================================
-- TABLE: multimodal_inputs
-- Stores all ingested operational data across all supported modalities.
-- =============================================================================
CREATE TABLE multimodal_inputs (
    id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    format            TEXT        NOT NULL CHECK (format IN ('text','json','pdf','image','log','audio','transcript')),
    file_path         TEXT,
    raw_content       TEXT,
    extracted_text    TEXT,
    transcript        TEXT,
    file_size_bytes   BIGINT,
    processing_status TEXT        NOT NULL CHECK (processing_status IN ('pending','processing','ready','failed')),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- =============================================================================
-- TABLE: incidents
-- Represents a classified operational event requiring remediation.
-- Depends on: multimodal_inputs, workflows (forward ref resolved below)
-- =============================================================================
CREATE TABLE incidents (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    root_signature   TEXT        NOT NULL,
    severity         TEXT        CHECK (severity IN ('critical','high','medium','low')),
    confidence_score FLOAT       CHECK (confidence_score BETWEEN 0.0 AND 1.0),
    status           TEXT        NOT NULL CHECK (status IN ('open','in_progress','resolved','escalated')),
    source_input_ref UUID        REFERENCES multimodal_inputs(id),
    workflow_id      UUID,       -- FK to workflows added after workflows table is created
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Composite index for deduplication queries (Requirement 1.4: 60-second window dedup)
CREATE INDEX idx_incidents_root_signature ON incidents(root_signature, created_at);
CREATE INDEX idx_incidents_status         ON incidents(status);

-- =============================================================================
-- TABLE: workflows
-- Represents an execution plan and its runtime state for an incident.
-- =============================================================================
CREATE TABLE workflows (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_id      UUID        NOT NULL REFERENCES incidents(id),
    plan             JSONB       NOT NULL,
    status           TEXT        NOT NULL CHECK (status IN ('planning','executing','suspended','completed','failed')),
    current_step_ids UUID[],
    retry_count      INT         NOT NULL DEFAULT 0,
    checkpoint       JSONB,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_workflows_incident_id ON workflows(incident_id);
CREATE INDEX idx_workflows_status      ON workflows(status);

-- Now that workflows exists, add the FK from incidents.workflow_id
ALTER TABLE incidents
    ADD CONSTRAINT fk_incidents_workflow_id
    FOREIGN KEY (workflow_id) REFERENCES workflows(id);

-- =============================================================================
-- TABLE: workflow_steps
-- Individual atomic steps within a workflow execution plan.
-- Partitioned by RANGE on created_at for scalable retention (Requirement 8.6).
-- =============================================================================
CREATE TABLE workflow_steps (
    id          UUID        NOT NULL DEFAULT gen_random_uuid(),
    workflow_id UUID        NOT NULL REFERENCES workflows(id),
    agent_type  TEXT        NOT NULL CHECK (agent_type IN (
                    'planner','incident_analysis','operations','compliance',
                    'validation','recovery','escalation','memory')),
    action      JSONB       NOT NULL,
    status      TEXT        NOT NULL CHECK (status IN ('pending','active','completed','failed','suspended')),
    depends_on  UUID[],
    risk_score  FLOAT       CHECK (risk_score BETWEEN 0.0 AND 10.0),
    output      JSONB,
    retry_count INT         NOT NULL DEFAULT 0,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id, created_at)
) PARTITION BY RANGE (created_at);

CREATE INDEX idx_steps_workflow_id ON workflow_steps(workflow_id);
CREATE INDEX idx_steps_status      ON workflow_steps(status);

-- =============================================================================
-- TABLE: audit_trail
-- Immutable, append-only, hash-chained record of every agent action.
-- Partitioned by RANGE on created_at for scalable 90-day retention (Requirement 8.6).
-- Append-only rules enforce tamper-evidence (Requirement 8.5).
-- =============================================================================
CREATE TABLE audit_trail (
    id                 BIGINT      NOT NULL GENERATED ALWAYS AS IDENTITY,
    event_type         TEXT        NOT NULL,
    timestamp          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    agent_identity     TEXT        NOT NULL,
    incident_id        UUID        REFERENCES incidents(id),
    workflow_id        UUID        REFERENCES workflows(id),
    action_description TEXT        NOT NULL,
    inputs             JSONB,
    outputs            JSONB,
    risk_score         FLOAT,
    prev_entry_hash    TEXT        NOT NULL,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id, created_at)
) PARTITION BY RANGE (created_at);

-- Append-only enforcement: prevent UPDATE and DELETE on audit_trail (Requirement 8.5)
CREATE RULE no_update_audit AS ON UPDATE TO audit_trail DO INSTEAD NOTHING;
CREATE RULE no_delete_audit AS ON DELETE TO audit_trail DO INSTEAD NOTHING;

-- Indexes for audit query performance (Requirement 8.7: results within 3 seconds)
CREATE INDEX idx_audit_incident_id    ON audit_trail(incident_id);
CREATE INDEX idx_audit_workflow_id    ON audit_trail(workflow_id);
CREATE INDEX idx_audit_timestamp      ON audit_trail(timestamp);
CREATE INDEX idx_audit_event_type     ON audit_trail(event_type);
CREATE INDEX idx_audit_agent_identity ON audit_trail(agent_identity);

-- =============================================================================
-- TABLE: policies
-- Governance policies for risk thresholds, permissions, anomaly detection, retention.
-- =============================================================================
CREATE TABLE policies (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    name        TEXT        NOT NULL UNIQUE,
    version     INT         NOT NULL DEFAULT 1,
    is_active   BOOLEAN     NOT NULL DEFAULT TRUE,
    policy_type TEXT        NOT NULL CHECK (policy_type IN ('risk_threshold','permission','anomaly','retention')),
    config      JSONB       NOT NULL,
    created_by  TEXT        NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_policies_active ON policies(is_active);

-- =============================================================================
-- TABLE: operational_context
-- Long-term memory store for incident resolutions, agent metrics, policy decisions.
-- Uses pgvector for semantic similarity search (Requirement 10.3, 10.4).
-- =============================================================================
CREATE TABLE operational_context (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    context_type     TEXT        NOT NULL CHECK (context_type IN ('incident_resolution','agent_metric','policy_decision')),
    incident_id      UUID        REFERENCES incidents(id),
    agent_type       TEXT,
    content          JSONB       NOT NULL,
    embedding_vector VECTOR(1536),  -- pgvector: 1536-dim embeddings for semantic search
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_context_type    ON operational_context(context_type);
-- GIN index on JSONB content for full-text / containment queries (Requirement 10.4: < 500ms)
CREATE INDEX idx_context_content ON operational_context USING GIN(content);
