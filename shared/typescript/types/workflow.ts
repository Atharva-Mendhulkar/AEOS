/**
 * Workflow, step, and execution plan types.
 * Mirrors the Python models in shared/python/aeos_shared/models/workflow.py
 */

export type WorkflowStatus =
  | 'planning'
  | 'executing'
  | 'suspended'
  | 'completed'
  | 'failed';

export type StepStatus =
  | 'pending'
  | 'active'
  | 'completed'
  | 'failed'
  | 'suspended';

export type AgentType =
  | 'planner'
  | 'incident_analysis'
  | 'operations'
  | 'compliance'
  | 'validation'
  | 'recovery'
  | 'escalation'
  | 'memory';

export interface ActionDescriptor {
  tool: string;
  params: Record<string, unknown>;
  timeout_seconds: number;
}

export interface WorkflowStep {
  id: string;
  workflow_id: string;
  agent_type: AgentType;
  action: ActionDescriptor;
  status: StepStatus;
  depends_on: string[];
  risk_score: number | null;
  output: Record<string, unknown> | null;
  retry_count: number;
  created_at: string;
  updated_at: string;
}

export interface ExecutionPlan {
  steps: WorkflowStep[];
  metadata: Record<string, unknown>;
}

export interface Workflow {
  id: string;
  incident_id: string;
  plan: ExecutionPlan | null;
  status: WorkflowStatus;
  current_step_ids: string[];
  retry_count: number;
  checkpoint: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

/**
 * A node in the dependency graph representing a single workflow step.
 */
export interface DependencyGraphNode {
  step_id: string;
  agent_type: AgentType;
  status: StepStatus;
  depends_on: string[];
  /** Step IDs that depend on this node */
  dependents: string[];
}

/**
 * Live dependency graph maintained by the Coordinator per active workflow.
 * Mirrors the in-memory DAG stored in Redis.
 * Satisfies Requirement 4.3.
 */
export interface DependencyGraph {
  workflow_id: string;
  nodes: Record<string, DependencyGraphNode>;
  /** Topologically sorted step IDs (root steps first) */
  execution_order: string[];
}
