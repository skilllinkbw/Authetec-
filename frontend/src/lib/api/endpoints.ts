/**
 * Typed endpoint wrappers — one function per backend route.
 * Mirrors the FastAPI surface; the frontend invents no parallel services.
 */
import { apiRequest } from "./client";
import type {
  AiScreenResult, Alert, AuditEntry, EngineResult, Evidence, HealthOut,
  SignatureResult, SocialScoreResult,
} from "../../types/api";

export interface AlertList { alerts: Alert[]; count: number }
export interface AuditList { entries: AuditEntry[]; count: number }
export interface AuditIntegrity { valid: boolean; entries_checked: number; checked_at: string }
export interface EvidenceList { evidence: Evidence[]; count: number }
export interface AlertAction {
  alert_id: string; status: string; updated: boolean; assigned_to?: string | null;
}
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

export function assignAlert(alertId: string, assignee: string): Promise<AlertAction> {
  return apiRequest<AlertAction>(`/api/v1/alerts/${encodeURIComponent(alertId)}/assign`,
    { method: "POST", body: JSON.stringify({ assignee }) });
}

export function addAlertNote(alertId: string, text: string,
  author = "analyst"): Promise<AlertAction> {
  return apiRequest<AlertAction>(`/api/v1/alerts/${encodeURIComponent(alertId)}/notes`,
    { method: "POST", body: JSON.stringify({ text, author }) });
}

export function scoreSocial(profile: Record<string, unknown>): Promise<SocialScoreResult> {
  return apiRequest<SocialScoreResult>("/api/v1/social/score",
    { method: "POST", body: JSON.stringify(profile) });
}

export function screenAi(payload: { text: string; context?: string; mode?: string })
  : Promise<AiScreenResult> {
  return apiRequest<AiScreenResult>("/api/v1/security/ai/screen",
    { method: "POST", body: JSON.stringify(payload) });
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
