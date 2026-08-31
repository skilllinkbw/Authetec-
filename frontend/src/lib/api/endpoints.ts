/**
 * Typed endpoint wrappers — one function per backend route.
 * Mirrors the FastAPI surface; the frontend invents no parallel services.
 */
import { apiRequest } from "./client";
import type {
  Alert, AuditEntry, EngineResult, Evidence, HealthOut, SignatureResult,
} from "../../types/api";

export interface AlertList { alerts: Alert[]; count: number }
export interface AuditList { entries: AuditEntry[]; count: number }
export interface AuditIntegrity { valid: boolean; entries_checked: number; checked_at: string }
export interface EvidenceList { evidence: Evidence[]; count: number }
export interface AlertAction { alert_id: string; status: string; updated: boolean }
export interface PaymentScore { transaction_id: string; result: EngineResult }

export function getHealth(): Promise<HealthOut> {
  return apiRequest<HealthOut>("/health");
}

export function scorePayment(tx: Record<string, unknown>): Promise<PaymentScore> {
  return apiRequest<PaymentScore>("/api/v1/payments/score",
    { method: "POST", body: JSON.stringify(tx) });
}

export function verifyDocument(file: File, expectedType: string): Promise<EngineResult> {
  const form = new FormData();
  form.append("file", file);
  const qs = expectedType ? `?expected_type=${encodeURIComponent(expectedType)}` : "";
  return apiRequest<EngineResult>(`/api/v1/verification/documents${qs}`,
    { method: "POST", body: form });
}

export function enrollSignature(payload: {
  owner_id: string; label?: string; image_b64: string; monitored?: boolean;
}): Promise<SignatureResult> {
  return apiRequest<SignatureResult>("/api/v1/verification/signatures/enroll",
    { method: "POST", body: JSON.stringify(payload) });
}

export function verifySignature(payload: {
  owner_id: string; reference_id?: string; image_b64: string;
}): Promise<SignatureResult> {
  return apiRequest<SignatureResult>("/api/v1/verification/signatures/verify",
    { method: "POST", body: JSON.stringify(payload) });
}

export function listAlerts(status?: string): Promise<AlertList> {
  const qs = status ? `?status=${encodeURIComponent(status)}` : "";
  return apiRequest<AlertList>(`/api/v1/alerts${qs}`);
}

export function acknowledgeAlert(alertId: string): Promise<AlertAction> {
  return apiRequest<AlertAction>(`/api/v1/alerts/${encodeURIComponent(alertId)}/acknowledge`,
    { method: "POST" });
}

export function resolveAlert(alertId: string): Promise<AlertAction> {
  return apiRequest<AlertAction>(`/api/v1/alerts/${encodeURIComponent(alertId)}/resolve`,
    { method: "POST" });
}

export function listAudit(limit = 50): Promise<AuditList> {
  return apiRequest<AuditList>(`/api/v1/audit?limit=${limit}`);
}

export function auditIntegrity(): Promise<AuditIntegrity> {
  return apiRequest<AuditIntegrity>("/api/v1/audit/integrity");
}

export function listEvidence(limit = 50): Promise<EvidenceList> {
  return apiRequest<EvidenceList>(`/api/v1/evidence?limit=${limit}`);
}
