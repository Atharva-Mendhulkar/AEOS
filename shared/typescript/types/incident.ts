/**
 * Incident and multimodal input types.
 * Mirrors the Python models in shared/python/aeos_shared/models/incident.py
 */

export type MultimodalInputFormat =
  | 'text'
  | 'json'
  | 'pdf'
  | 'image'
  | 'log'
  | 'audio'
  | 'transcript';

export type MultimodalInputStatus =
  | 'pending'
  | 'processing'
  | 'ready'
  | 'failed';

export type IncidentSeverity = 'critical' | 'high' | 'medium' | 'low';

export type IncidentStatus = 'open' | 'in_progress' | 'resolved' | 'escalated';

export interface MultimodalInput {
  id: string;
  format: MultimodalInputFormat;
  file_path: string | null;
  raw_content: string | null;
  extracted_text: string | null;
  transcript: string | null;
  file_size_bytes: number | null;
  processing_status: MultimodalInputStatus;
  created_at: string;
}

export interface Incident {
  id: string;
  root_signature: string;
  severity: IncidentSeverity | null;
  confidence_score: number | null;
  status: IncidentStatus;
  source_input_ref: string | null;
  workflow_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface ClassificationResult {
  severity: IncidentSeverity | null;
  confidence_score: number;
  root_signature: string;
  requires_escalation: boolean;
}
