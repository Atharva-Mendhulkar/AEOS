/**
 * Agent task, result, and capability types.
 * Mirrors the Python AgentTask model from the design spec (L4 Specialist Agent Layer).
 * Satisfies Requirement 4.3.
 */

import type { ActionDescriptor, AgentType } from './workflow.js';

export interface PermissionScope {
  agent_type: AgentType;
  allowed_resources: string[];
  denied_resources: string[];
  allowed_api_scopes: string[];
}

export interface OperationalContext {
  incident_id: string | null;
  historical_resolutions: Record<string, unknown>[];
  agent_metrics: Record<string, unknown>;
  policy_constraints: Record<string, unknown>;
}

/**
 * Task dispatched by the Coordinator to a Specialist Agent via Redis pub-sub.
 * Mirrors the Python AgentTask class in the design spec.
 */
export interface AgentTask {
  task_id: string;
  workflow_id: string;
  step_id: string;
  incident_id: string;
  action: ActionDescriptor;
  context: OperationalContext;
  permissions: PermissionScope;
}

export interface AgentResult {
  task_id: string;
  step_id: string;
  workflow_id: string;
  success: boolean;
  output: Record<string, unknown> | null;
  error: string | null;
  requires_escalation: boolean;
}

export type AgentState = 'active' | 'idle' | 'blocked';

export interface AgentCapabilities {
  agent_type: AgentType;
  supported_action_types: string[];
  max_concurrent_tasks: number;
}

export interface HealthStatus {
  agent_type: AgentType;
  status: 'healthy' | 'degraded' | 'unhealthy';
  message: string | null;
  checked_at: string;
}
