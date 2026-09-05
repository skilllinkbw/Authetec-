/**
 * AI Security console — screens AI prompts/outputs for prompt-injection
 * indicators and credential leakage before they reach a model or get
 * stored. Renders the structured verdict and detection signals.
 */
import { useState } from "react";
import { screenAi } from "../lib/api/endpoints";
import { ApiError } from "../lib/api/client";
import { formatScore } from "../lib/format";
import { Badge, Card, ErrorBox, PageTitle, RiskScore } from "../components/ui";
import type { AiScreenResult } from "../types/api";

export default function AiSecurity() {
  const [text, setText] = useState("");
  const [mode, setMode] = useState<"prompt" | "output">("prompt");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [result, setResult] = useState<AiScreenResult | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setError(null); setResult(null);
    try {
      if (!text.trim()) {
        throw new ApiError(400, "client_validation", "Screened content is required.");
      }
      setResult(await screenAi({ text, mode }));
    } catch (err) {
      setError(err instanceof ApiError ? err
        : new ApiError(0, "unknown_error", "An unexpected error occurred."));
    } finally {
      setBusy(false);
    }
  }

  const tone = result?.decision === "CLEAR" ? "success"
    : result?.decision === "BLOCK" ? "danger" : "warning";

  return (
    <>
      <PageTitle
        title="AI Security"
        subtitle="Policy guard-rails around AI use: injection screening, credential-leak detection and validation."
      />

      <Card title="Screen AI content">
        <form onSubmit={submit}>
          <label className="field">
            <span>Content to screen</span>
            <textarea rows={6} value={text}
              aria-label="Content to screen"
              placeholder="Paste a prompt or model output to scan…"
              onChange={(e) => setText(e.target.value)} />
          </label>
          <div style={{ display: "flex", gap: 12, alignItems: "center", marginTop: 8 }}>
            <label className="field" style={{ maxWidth: 200 }}>
              <span>Mode</span>
              <select value={mode} onChange={(e) => setMode(e.target.value as "prompt" | "output")}>
                <option value="prompt">Prompt (inbound)</option>
                <option value="output">Output (outbound)</option>
              </select>
            </label>
            <button className="btn" type="submit" disabled={busy}>
              {busy ? "Screening…" : "Screen content"}
            </button>
          </div>
        </form>
      </Card>

      {error && <div className="mt"><ErrorBox error={error} /></div>}
      {result && (
        <div className="mt">
          <Card title="Screening record">
            <div className="card-grid grid-4 mb">
              <div>
                <p className="stat-label">Verdict</p>
                <Badge tone={tone as "success" | "danger" | "warning"}>{result.decision}</Badge>
              </div>
              <div>
                <p className="stat-label">Injection score</p>
                <strong>{formatScore(result.prompt_injection_score)}</strong>
              </div>
              <div>
                <p className="stat-label">Secret-leak score</p>
                <RiskScore score={result.secret_leak_score} />
              </div>
              <div>
                <p className="stat-label">Validation</p>
                <Badge tone={result.validation_valid ? "success" : "warning"}>
                  {result.validation_valid ? "VALID" : "INVALID"}
                </Badge>
              </div>
            </div>

            <h2 style={{ fontSize: 13.5 }}>Why this verdict</h2>
            <ul style={{ paddingLeft: 20, fontSize: 13.5 }}>
              {result.reasons.map((r, i) => <li key={i}>{r}</li>)}
            </ul>

            {result.signals.length > 0 && (
              <div className="table-wrap mt">
                <table className="data">
                  <thead>
                    <tr><th scope="col">Detection</th><th scope="col">Severity</th><th scope="col">Detail</th></tr>
                  </thead>
                  <tbody>
                    {result.signals.map((s, i) => (
                      <tr key={`${s.name}-${i}`}>
                        <td className="mono">{s.name}</td>
                        <td>{s.severity.toFixed(2)}</td>
                        <td className="mono" style={{ fontSize: 12 }}>{s.detail}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            <p className="muted mt" style={{ fontSize: 12 }}>
              Screening <span className="mono">{result.screening_id}</span> · Model:{" "}
              <span className="mono">{result.model_version}</span> · {result.timestamp}
            </p>
          </Card>
        </div>
      )}
    </>
  );
}