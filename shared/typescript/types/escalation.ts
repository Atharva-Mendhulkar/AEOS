/**
 * Escalation record types.
 * Mirrors the EscalationRequest / EscalationRecord Python models.
 * Satisfies Requirements 7.1, 7.2, 7.3, 7.4, 7.5.
 */

import type { IncidentSeverity } from './incident.js';

export type EscalationDecision = 'approve' | 'reject' | 'modify';

export type EscalationStatus =
  | 'pending'
  | 'approved'
  | 'rejected'
  | 'modified'
  | 'timed_out'
  | 'escalated_tier2';

export interface EscalationOption {
  value: EscalationDecision;
  label: string;
  description: string | null;
}

/**
 * Structured escalation request presented to the human operator.
 * All required fields per Requirement 7.1.
 */
export interface EscalationRequest {
  escalation_id: string;
  incident_id: string;
  workflow_id: string;
  step_id: string;
  incident_summary: string;
  proposed_action: Record<string, unknown>;
  risk_score: number;
  options: EscalationOption[];
  severity: IncidentSeverity | null;
  created_at: string;
  timeout_at: string;
}

/**
 * Persisted escalation record including operator response.
 */
export interface EscalationRecord {
  id: string;
  incident_id: string;
  workflow_id: string;
  step_id: string;
  request: EscalationRequest;
  status: EscalationStatus;
  decision: EscalationDecision | null;
  operator_id: string | null;
  operator_notes: string | null;
  modified_action: Record<string, unknown> | null;
  resolved_at: string | null;
  created_at: string;
  updated_at: string;
}
