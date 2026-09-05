/**
 * Developer platform — API surface catalog, usage notes and an honest
 * module status matrix. API keys are issued by the operator; the raw key
 * is never displayed again after creation (only masked hints).
 */
import { Card, PageTitle, Badge } from "../components/ui";
import { getMaskedApiKey, hasApiKey } from "../lib/api/client";

const ENDPOINTS = [
  { method: "GET", path: "/health", desc: "Component health (database, vector store, alerts, models)" },
  { method: "POST", path: "/api/v1/verification/documents", desc: "Verify a document (multipart upload)" },
  { method: "POST", path: "/api/v1/verification/signatures/enroll", desc: "Enroll a reference signature" },
  { method: "POST", path: "/api/v1/verification/signatures/verify", desc: "Verify a signature against a reference" },
  { method: "POST", path: "/api/v1/payments/score", desc: "Score a transaction for fraud risk" },
  { method: "POST", path: "/api/v1/risk/aggregate", desc: "Aggregate engine results into a unified decision" },
  { method: "GET", path: "/api/v1/alerts", desc: "List tenant alerts (status filter)" },
  { method: "POST", path: "/api/v1/alerts/{id}/acknowledge", desc: "Acknowledge an alert" },
  { method: "POST", path: "/api/v1/alerts/{id}/resolve", desc: "Resolve an alert" },
  { method: "GET", path: "/api/v1/audit", desc: "Recent audit entries (tenant-scoped)" },
  { method: "GET", path: "/api/v1/audit/integrity", desc: "Verify the audit hash chain" },
  { method: "GET", path: "/api/v1/evidence", desc: "List evidence references" },
  { method: "GET", path: "/api/v1/evidence/{id}", desc: "Fetch one evidence reference" },
];

const MODULE_STATUS = [
  { module: "Document Verification", status: "OPERATIONAL", note: "Rule-based + heuristic pipeline; OCR depends on installed engine" },
  { module: "Signature Verification & Guard", status: "OPERATIONAL", note: "Shape-similarity model; advisory, not proof of authorship" },
  { module: "Payment Fraud Scoring", status: "OPERATIONAL", note: "Rules-based fallback; LightGBM model requires registry promotion" },
  { module: "Unified Risk Engine", status: "OPERATIONAL", note: "Confidence-weighted aggregation, configurable thresholds" },
  { module: "Alerts / Audit / Evidence", status: "OPERATIONAL", note: "In-memory in dev; Supabase-persisted when configured" },
  { module: "Accuracy Benchmarks", status: "EXPERIMENTAL", note: "Fraud-model benchmark reports exist under benchmarks/reports; per-module validation gates in progress" },
  { module: "Face / Liveness Verification", status: "REQUIRES EXTERNAL INTEGRATION", note: "Not implemented — no capability is claimed" },
  { module: "Certificate Registry Lookup", status: "REQUIRES EXTERNAL INTEGRATION", note: "Issuer adapters to be built per institution" },
  { module: "Social Trust Engine", status: "PLANNED", note: "Lawful-API design phase" },
  { module: "Webhooks / Cases / RBAC", status: "PLANNED", note: "Architecture defined; implementation scheduled" },
];

export default function Developers() {
  return (
    <>
      <PageTitle
        title="Developers"
        subtitle="Trust API surface, integration guidance and platform capability status."
      />

      <Card title="API status">
        <p style={{ fontSize: 13.5 }}>
          {hasApiKey()
            ? <>API key configured for this session (<span className="mono">{getMaskedApiKey()}</span>).</>
            : "No API key configured. Set one in the top bar if this deployment requires authentication."}
        </p>
        <p className="muted" style={{ fontSize: 13 }}>
          Rate limits: 120 requests/minute per API key or workspace (configurable).
          Rate-limited responses return HTTP 429 with a <span className="mono">Retry-After</span> header
          and a correlation ID.
        </p>
      </Card>

      <Card title="Endpoint catalog" className="mt">
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr><th scope="col">Method</th><th scope="col">Path</th><th scope="col">Description</th></tr>
            </thead>
            <tbody>
              {ENDPOINTS.map((e) => (
                <tr key={e.path + e.method}>
                  <td><span className="badge badge-info">{e.method}</span></td>
                  <td className="mono">{e.path}</td>
                  <td>{e.desc}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <Card title="Quickstart" className="mt">
        <pre className="mono" style={{ background: "#0f172a", color: "#e2e8f0",
          padding: 14, borderRadius: 8, overflowX: "auto", fontSize: 12.5 }}>
{`curl -X POST http://localhost:8000/api/v1/payments/score \\
  -H "Content-Type: application/json" \\
  -H "X-Tenant-ID: my-tenant" \\
  ${hasApiKey() ? '-H "X-API-Key: <your-key>" \\\n  ' : ""}-d '{"transaction_id":"tx-001","amount":150.00,"channel":"card"}'`}
        </pre>
        <p className="muted" style={{ fontSize: 12.5 }}>
          Interactive OpenAPI docs are available at <span className="mono">/docs</span> on the
          API server in non-production environments.
        </p>
      </Card>


      <Card title="Module capability status" className="mt">
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr><th scope="col">Module</th><th scope="col">Status</th><th scope="col">Notes</th></tr>
            </thead>
            <tbody>
              {MODULE_STATUS.map((m) => (
                <tr key={m.module}>
                  <td>{m.module}</td>
                  <td><Badge tone={m.status === "OPERATIONAL" ? "success"
                    : m.status === "EXPERIMENTAL" ? "warning" : "neutral"}>
                    {m.status}</Badge></td>
                  <td>{m.note}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="muted mt" style={{ fontSize: 12 }}>
          No accuracy figure is advertised for any module until it has been
          measured against a labelled validation dataset (see benchmarks/reports).
        </p>
      </Card>
    </>
  );
}
