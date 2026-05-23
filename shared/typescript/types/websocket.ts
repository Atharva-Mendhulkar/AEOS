/**
 * WebSocket event types for the AEOS real-time event stream.
 * Mirrors the event table in the design spec (WebSocket Events section).
 * Satisfies Requirements 8.2, 4.6.
 *
 * Clients connect to: wss://<host>/ws/events?token=<jwt>
 * On reconnect, send: { type: "subscribe", last_sequence: number }
 */

import type { AgentState } from './agent.js';
import type { EscalationDecision } from './escalation.js';
import type { IncidentSeverity } from './incident.js';
import type { AgentType } from './workflow.js';

// ---------------------------------------------------------------------------
// Event type literals — one for every event in the design spec event table
// ---------------------------------------------------------------------------

/** AC-01-005: Incident classified by the Incident Analysis Agent */
export type IncidentClassifiedEventType = 'incident.classified';

/** AC-04-002: A workflow step has been activated and dispatched to an agent */
export type StepStartedEventType = 'step.started';

/** AC-04-006: A workflow step completed successfully */
export type StepCompletedEventType = 'step.completed';

/** AC-06-001: A workflow step failed */
export type StepFailedEventType = 'step.failed';

/** AC-05-005: An Approval Gate was triggered; execution suspended */
export type EscalationTriggeredEventType = 'escalation.triggered';

/** AC-07-002/3: An escalation was resolved by an operator */
export type EscalationResolvedEventType = 'escalation.resolved';

/** AC-05-003: A Circuit Breaker was activated; step halted permanently */
export type CircuitBreakerActivatedEventType = 'circuit_breaker.activated';

/** AC-04-006: All steps in a workflow reached terminal state */
export type WorkflowCompletedEventType = 'workflow.completed';

/** AC-05-007: An anomalous execution pattern was detected */
export type AnomalyDetectedEventType = 'anomaly.detected';

/** AC-12-003: A governance policy was updated and applied */
export type PolicyUpdatedEventType = 'policy.updated';

/** AC-08-004: An agent changed its operational state */
export type AgentStateChangedEventType = 'agent.state_changed';

/** Union of all WebSocket event type literals */
export type WebSocketEventType =
  | IncidentClassifiedEventType
  | StepStartedEventType
  | StepCompletedEventType
  | StepFailedEventType
  | EscalationTriggeredEventType
  | EscalationResolvedEventType
  | CircuitBreakerActivatedEventType
  | WorkflowCompletedEventType
  | AnomalyDetectedEventType
  | PolicyUpdatedEventType
  | AgentStateChangedEventType;

// ---------------------------------------------------------------------------
// Per-event payload interfaces
// ---------------------------------------------------------------------------

export interface IncidentClassifiedPayload {
  incident_id: string;
  severity: IncidentSeverity;
  confidence_score: number;
  source_input_ref: string | null;
  timestamp: string;
}

export interface StepStartedPayload {
  workflow_id: string;
  step_id: string;
  agent_type: AgentType;
  action: Record<string, unknown>;
  timestamp: string;
}

export interface StepCompletedPayload {
  workflow_id: string;
  step_id: string;
  output: Record<string, unknown> | null;
  timestamp: string;
}

export type FailureType = 'transient' | 'permanent';

export interface StepFailedPayload {
  workflow_id: string;
  step_id: string;
  error: string;
  failure_type: FailureType;
  timestamp: string;
}

export interface EscalationTriggeredPayload {
  escalation_id: string;
  incident_id: string;
  risk_score: number;
  action_description: string;
  options: EscalationDecision[];
  timestamp: string;
}

export interface EscalationResolvedPayload {
  escalation_id: string;
  decision: EscalationDecision;
  operator_id: string;
  timestamp: string;
}

export interface CircuitBreakerActivatedPayload {
  workflow_id: string;
  step_id: string;
  risk_score: number;
  reason: string;
  timestamp: string;
}

export type WorkflowOutcome = 'success' | 'partial_failure' | 'failed';

export interface WorkflowCompletedPayload {
  workflow_id: string;
  incident_id: string;
  outcome: WorkflowOutcome;
  duration_ms: number;
  timestamp: string;
}

export interface AnomalyDetectedPayload {
  pattern_id: string;
  description: string;
  baseline_deviation: number;
  timestamp: string;
}

export interface PolicyUpdatedPayload {
  policy_id: string;
  version: number;
  applied_at: string;
  operator_id: string;
}

export interface AgentStateChangedPayload {
  agent_type: AgentType;
  agent_instance_id: string;
  state: AgentState;
  timestamp: string;
}

// ---------------------------------------------------------------------------
// Discriminated union — WebSocketEvent
// ---------------------------------------------------------------------------

export interface IncidentClassifiedEvent {
  type: IncidentClassifiedEventType;
  sequence: number;
  payload: IncidentClassifiedPayload;
}

export interface StepStartedEvent {
  type: StepStartedEventType;
  sequence: number;
  payload: StepStartedPayload;
}

export interface StepCompletedEvent {
  type: StepCompletedEventType;
  sequence: number;
  payload: StepCompletedPayload;
}

export interface StepFailedEvent {
  type: StepFailedEventType;
  sequence: number;
  payload: StepFailedPayload;
}

export interface EscalationTriggeredEvent {
  type: EscalationTriggeredEventType;
  sequence: number;
  payload: EscalationTriggeredPayload;
}

export interface EscalationResolvedEvent {
  type: EscalationResolvedEventType;
  sequence: number;
  payload: EscalationResolvedPayload;
}

export interface CircuitBreakerActivatedEvent {
  type: CircuitBreakerActivatedEventType;
  sequence: number;
  payload: CircuitBreakerActivatedPayload;
}

export interface WorkflowCompletedEvent {
  type: WorkflowCompletedEventType;
  sequence: number;
  payload: WorkflowCompletedPayload;
}

export interface AnomalyDetectedEvent {
  type: AnomalyDetectedEventType;
  sequence: number;
  payload: AnomalyDetectedPayload;
}

export interface PolicyUpdatedEvent {
  type: PolicyUpdatedEventType;
  sequence: number;
  payload: PolicyUpdatedPayload;
}

export interface AgentStateChangedEvent {
  type: AgentStateChangedEventType;
  sequence: number;
  payload: AgentStateChangedPayload;
}

/**
 * Discriminated union of all WebSocket events emitted by the Observability Layer.
 * Use the `type` field to narrow to the specific event and access its typed payload.
 *
 * @example
 * function handleEvent(event: WebSocketEvent) {
 *   switch (event.type) {
 *     case 'incident.classified':
 *       console.log(event.payload.severity); // IncidentSeverity
 *       break;
 *     case 'step.started':
 *       console.log(event.payload.agent_type); // AgentType
 *       break;
 *   }
 * }
 */
export type WebSocketEvent =
  | IncidentClassifiedEvent
  | StepStartedEvent
  | StepCompletedEvent
  | StepFailedEvent
  | EscalationTriggeredEvent
  | EscalationResolvedEvent
  | CircuitBreakerActivatedEvent
  | WorkflowCompletedEvent
  | AnomalyDetectedEvent
  | PolicyUpdatedEvent
  | AgentStateChangedEvent;

// ---------------------------------------------------------------------------
// WebSocket reconnection protocol message
// ---------------------------------------------------------------------------

export interface WebSocketSubscribeMessage {
  type: 'subscribe';
  last_sequence: number;
}
