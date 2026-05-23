-- =============================================================================
-- AEOS Control Panel — Monthly Partitions for 2026
-- Migration: 002_partitions_2026.sql
-- Requirements: 8.6 (90-day retention, scalable partition management)
--
-- Creates monthly range partitions for:
--   - audit_trail       (partitioned by created_at)
--   - workflow_steps    (partitioned by created_at)
--
-- Naming convention: <table>_y<YYYY>m<MM>
-- Each partition covers [first day of month, first day of next month).
-- =============================================================================

-- =============================================================================
-- audit_trail partitions — 2026
-- =============================================================================

CREATE TABLE audit_trail_y2026m01 PARTITION OF audit_trail
    FOR VALUES FROM ('2026-01-01 00:00:00+00') TO ('2026-02-01 00:00:00+00');

CREATE TABLE audit_trail_y2026m02 PARTITION OF audit_trail
    FOR VALUES FROM ('2026-02-01 00:00:00+00') TO ('2026-03-01 00:00:00+00');

CREATE TABLE audit_trail_y2026m03 PARTITION OF audit_trail
    FOR VALUES FROM ('2026-03-01 00:00:00+00') TO ('2026-04-01 00:00:00+00');

CREATE TABLE audit_trail_y2026m04 PARTITION OF audit_trail
    FOR VALUES FROM ('2026-04-01 00:00:00+00') TO ('2026-05-01 00:00:00+00');

CREATE TABLE audit_trail_y2026m05 PARTITION OF audit_trail
    FOR VALUES FROM ('2026-05-01 00:00:00+00') TO ('2026-06-01 00:00:00+00');

CREATE TABLE audit_trail_y2026m06 PARTITION OF audit_trail
    FOR VALUES FROM ('2026-06-01 00:00:00+00') TO ('2026-07-01 00:00:00+00');

CREATE TABLE audit_trail_y2026m07 PARTITION OF audit_trail
    FOR VALUES FROM ('2026-07-01 00:00:00+00') TO ('2026-08-01 00:00:00+00');

CREATE TABLE audit_trail_y2026m08 PARTITION OF audit_trail
    FOR VALUES FROM ('2026-08-01 00:00:00+00') TO ('2026-09-01 00:00:00+00');

CREATE TABLE audit_trail_y2026m09 PARTITION OF audit_trail
    FOR VALUES FROM ('2026-09-01 00:00:00+00') TO ('2026-10-01 00:00:00+00');

CREATE TABLE audit_trail_y2026m10 PARTITION OF audit_trail
    FOR VALUES FROM ('2026-10-01 00:00:00+00') TO ('2026-11-01 00:00:00+00');

CREATE TABLE audit_trail_y2026m11 PARTITION OF audit_trail
    FOR VALUES FROM ('2026-11-01 00:00:00+00') TO ('2026-12-01 00:00:00+00');

CREATE TABLE audit_trail_y2026m12 PARTITION OF audit_trail
    FOR VALUES FROM ('2026-12-01 00:00:00+00') TO ('2027-01-01 00:00:00+00');

-- =============================================================================
-- workflow_steps partitions — 2026
-- =============================================================================

CREATE TABLE workflow_steps_y2026m01 PARTITION OF workflow_steps
    FOR VALUES FROM ('2026-01-01 00:00:00+00') TO ('2026-02-01 00:00:00+00');

CREATE TABLE workflow_steps_y2026m02 PARTITION OF workflow_steps
    FOR VALUES FROM ('2026-02-01 00:00:00+00') TO ('2026-03-01 00:00:00+00');

CREATE TABLE workflow_steps_y2026m03 PARTITION OF workflow_steps
    FOR VALUES FROM ('2026-03-01 00:00:00+00') TO ('2026-04-01 00:00:00+00');

CREATE TABLE workflow_steps_y2026m04 PARTITION OF workflow_steps
    FOR VALUES FROM ('2026-04-01 00:00:00+00') TO ('2026-05-01 00:00:00+00');

CREATE TABLE workflow_steps_y2026m05 PARTITION OF workflow_steps
    FOR VALUES FROM ('2026-05-01 00:00:00+00') TO ('2026-06-01 00:00:00+00');

CREATE TABLE workflow_steps_y2026m06 PARTITION OF workflow_steps
    FOR VALUES FROM ('2026-06-01 00:00:00+00') TO ('2026-07-01 00:00:00+00');

CREATE TABLE workflow_steps_y2026m07 PARTITION OF workflow_steps
    FOR VALUES FROM ('2026-07-01 00:00:00+00') TO ('2026-08-01 00:00:00+00');

CREATE TABLE workflow_steps_y2026m08 PARTITION OF workflow_steps
    FOR VALUES FROM ('2026-08-01 00:00:00+00') TO ('2026-09-01 00:00:00+00');

CREATE TABLE workflow_steps_y2026m09 PARTITION OF workflow_steps
    FOR VALUES FROM ('2026-09-01 00:00:00+00') TO ('2026-10-01 00:00:00+00');

CREATE TABLE workflow_steps_y2026m10 PARTITION OF workflow_steps
    FOR VALUES FROM ('2026-10-01 00:00:00+00') TO ('2026-11-01 00:00:00+00');

CREATE TABLE workflow_steps_y2026m11 PARTITION OF workflow_steps
    FOR VALUES FROM ('2026-11-01 00:00:00+00') TO ('2026-12-01 00:00:00+00');

CREATE TABLE workflow_steps_y2026m12 PARTITION OF workflow_steps
    FOR VALUES FROM ('2026-12-01 00:00:00+00') TO ('2027-01-01 00:00:00+00');
