/**
 * API type contracts — mirror app/schemas (Pydantic v2) exactly.
 * Single source of truth is the backend; these types are its client view.
 */

export type Decision = "CLEAR" | "REVIEW" | "BLOCK";

export interface Signal {
  name: string;
  value: number;
  weight: number;
  reason: string;
  source: string;
}

export interface EngineResult {
  engine: string;
  risk_score: number;
  confidence: number;
  decision: Decision;
  signals: Signal[];
  reasons: string[];
  evidence: Record<string, unknown>[];
  model_version: string;
  processing_time_ms: number;
  extra: Record<string, unknown>;
  timestamp: string;
}

export interface HealthOut {
  app: string;
  version: string;
  environment: string;
  status: string;
  components: { name: string; status: string; detail: Record<string, unknown> }[];
}

export interface Alert {
  alert_id: string;
  tenant_id: string;
  type: string;
  severity: "info" | "low" | "medium" | "high" | "critical";
  risk_score: number;
  source: string;
  evidence_ids: string[];
  message: string;
  status: "OPEN" | "ACKNOWLEDGED" | "RESOLVED";
  created_at: string;
  acknowledged_at: string | null;
  resolved_at: string | null;
  metadata: Record<string, unknown>;
}

export interface AuditEntry {
  event_id: string;
  event_type: string;
  actor_id: string;
  tenant_id: string;
  resource_type: string;
  resource_id: string;
  action: string;
  timestamp: string;
  correlation_id: string;
  request_id: string | null;
  result: string;
  metadata: Record<string, unknown>;
  prev_hash: string;
  hash: string;
}

export interface Evidence {
  evidence_id: string;
  tenant_id: string;
  storage_uri: string;
  content_type: string;
  purpose: string;
  created_at: string;
  metadata: Record<string, unknown>;
}

export interface SignatureResult {
  signature_id: string;
  result: EngineResult;
  metadata?: Record<string, unknown>;
}
