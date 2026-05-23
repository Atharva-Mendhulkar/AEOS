export type MultimodalInputFormat = 'text' | 'json' | 'pdf' | 'image' | 'log' | 'audio' | 'transcript';
export type MultimodalInputStatus = 'pending' | 'processing' | 'ready' | 'failed';
export type IncidentSeverity = 'critical' | 'high' | 'medium' | 'low';
export type IncidentStatus = 'open' | 'in_progress' | 'resolved' | 'escalated';

export interface MultimodalInput {
  id: string;
  format: MultimodalInputFormat;
  file_path?: string;
  raw_content?: string;
  extracted_text?: string;
  transcript?: string;
  file_size_bytes?: number;
  processing_status: MultimodalInputStatus;
  created_at: string;
}

export interface Incident {
  id: string;
  root_signature: string;
  severity?: IncidentSeverity;
  confidence_score?: number;
  status: IncidentStatus;
  source_input_ref?: string;
  workflow_id?: string;
  created_at: string;
  updated_at: string;
}

export interface ClassificationResult {
  severity?: IncidentSeverity;
  confidence_score: number;
  root_signature: string;
  requires_escalation: boolean;
}
