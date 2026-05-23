/**
 * Governance, policy, and audit trail types.
 * Mirrors the Python Policy, AuditTrailEntry, and related models.
 * Satisfies Requirements 5.1–5.7, 8.5, 12.1–12.5.
 */

export type PolicyType =
  | 'risk_threshold'
  | 'permission'
  | 'anomaly'
  | 'retention';

export interface Policy {
  id: string;
  name: string;
  version: number;
  is_active: boolean;
  policy_type: PolicyType;
  config: Record<string, unknown>;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface PolicyViolation {
  policy_id: string;
  policy_name: string;
  violation_type: string;
  description: string;
  step_id: string | null;
}

export interface RiskAssessment {
  score: number;
  factors: string[];
  scoring_method: 'rule_based' | 'llm';
}

export type GovernanceDecision = 'approved' | 'suspended' | 'halted' | 'rejected';

export interface ValidationResult {
  decision: GovernanceDecision;
  risk_assessment: RiskAssessment | null;
  violations: PolicyViolation[];
  escalation_id: string | null;
  reason: string | null;
}

export interface AuditTrailEntry {
  id: number;
  event_type: string;
  timestamp: string;
  agent_identity: string;
  incident_id: string | null;
  workflow_id: string | null;
  action_description: string;
  inputs: Record<string, unknown> | null;
  outputs: Record<string, unknown> | null;
  risk_score: number | null;
  prev_entry_hash: string;
}
