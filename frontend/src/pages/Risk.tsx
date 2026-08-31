/**
 * Risk Intelligence console — aggregates engine results into a unified
 * risk decision with full provenance. Intended for API integrators and
 * analysts composing multi-signal evaluations.
 */
import { useState } from "react";
import { ApiError } from "../lib/api/client";
import { apiRequest } from "../lib/api/client";
import {
  Card, ConfidenceMeter, DecisionBadge, ErrorBox, PageTitle,
} from "../components/ui";
import type { EngineResult } from "../types/api";

interface UnifiedRisk {
  risk_score: number;
  confidence: number;
  decision: string;
  contributing_signals: Record<string, number>;
  model_versions: Record<string, string>;
  evidence_ids: string[];
  correlation_id: string;
  reasons: string[];
}

export default function Risk() {
  const [engine, setEngine] = useState("payment");
  const [score, setScore] = useState("0.9");
  const [confidence, setConfidence] = useState("1.0");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [result, setResult] = useState<UnifiedRisk | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setError(null); setResult(null);
    try {
      const s = Number(score), c = Number(confidence);
      if (Number.isNaN(s) || s < 0 || s > 1 || Number.isNaN(c) || c < 0 || c > 1) {
        throw new ApiError(400, "client_validation",
          "Risk score and confidence must be numbers between 0 and 1.");
      }
      const engineResult: EngineResult = {
        engine, risk_score: s, confidence: c,
        decision: s >= 0.7 ? "BLOCK" : s >= 0.3 ? "REVIEW" : "CLEAR",
        signals: [], reasons: [], evidence: [],
        model_version: "operator-input", processing_time_ms: 0,
        extra: {}, timestamp: new Date().toISOString(),
      };
      setResult(await apiRequest<UnifiedRisk>("/api/v1/risk/aggregate", {
        method: "POST",
        body: JSON.stringify([engineResult]),
      }));
    } catch (err) {
      setError(err instanceof ApiError ? err
        : new ApiError(0, "unknown_error", "An unexpected error occurred."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageTitle
        title="Risk Intelligence"
        subtitle={"Aggregate engine outputs into one calibrated decision. " +
          "Weights, thresholds and contributions are explicit."}
      />

      <Card title="Aggregate engine results">
        <form onSubmit={submit}>
          <div className="card-grid grid-3">
            <label className="field">
              <span>Signal source</span>
              <select value={engine} onChange={(e) => setEngine(e.target.value)}>
                <option value="payment">payment</option>
                <option value="document">document</option>
                <option value="signature">signature</option>
                <option value="face">face</option>
                <option value="identity">identity</option>
                <option value="device">device</option>
                <option value="social">social</option>
              </select>
            </label>
            <label className="field">
              <span>Risk score (0–1)</span>
              <input type="number" min="0" max="1" step="0.01" value={score}
                onChange={(e) => setScore(e.target.value)} />
            </label>
            <label className="field">
              <span>Confidence (0–1)</span>
              <input type="number" min="0" max="1" step="0.01" value={confidence}
                onChange={(e) => setConfidence(e.target.value)} />
            </label>
          </div>
          <button className="btn" type="submit" disabled={busy}>
            {busy ? "Aggregating…" : "Aggregate"}
          </button>
        </form>
      </Card>

      {error && <div className="mt"><ErrorBox error={error} /></div>}

      {result && (
        <Card title="Unified risk decision" className="mt">
          <div className="card-grid grid-3 mb">
            <div>
              <p className="stat-label">Decision</p>
              <DecisionBadge decision={result.decision} />
            </div>
            <div>
              <p className="stat-label">Unified risk</p>
              <p className="stat-value" style={{ fontSize: 20 }}>
                {(result.risk_score * 100).toFixed(1)}%
              </p>
            </div>
            <div>
              <ConfidenceMeter value={result.confidence} />
            </div>
          </div>
          <h2 style={{ fontSize: 13.5 }}>Contributing signals</h2>
          <table className="data">
            <thead>
              <tr><th scope="col">Source</th><th scope="col">Normalised contribution</th></tr>
            </thead>
            <tbody>
              {Object.entries(result.contributing_signals).map(([src, val]) => (
                <tr key={src}>
                  <td className="mono">{src}</td>
                  <td>{(val * 100).toFixed(1)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
          <ul style={{ paddingLeft: 20, fontSize: 13.5 }} className="mt">
            {result.reasons.map((r, i) => <li key={i}>{r}</li>)}
          </ul>
          <p className="muted mt" style={{ fontSize: 12 }}>
            Correlation ID: <span className="mono">{result.correlation_id}</span>
          </p>
        </Card>
      )}
    </>
  );
}
