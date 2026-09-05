/**
 * Shared presentational components — small, reusable, accessible.
 * All verification results render through these so confidence, risk and
 * decisions are visualised consistently across modules.
 */
import type { ReactNode } from "react";
import { decisionLabel, formatScore, riskTone } from "../lib/format";
import type { EngineResult, Signal } from "../types/api";

export function PageTitle({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <div className="mb">
      <h1 style={{ fontSize: 20 }}>{title}</h1>
      {subtitle && <p className="muted" style={{ fontSize: 13.5 }}>{subtitle}</p>}
    </div>
  );
}

export function Card({ title, children, className }: {
  title?: string; children: ReactNode; className?: string;
}) {
  return (
    <section className={`card ${className ?? ""}`} aria-label={title}>
      {title && <h2>{title}</h2>}
      {children}
    </section>
  );
}

const TONE_CLASS = {
  success: "badge-success",
  warning: "badge-warning",
  danger: "badge-danger",
  neutral: "badge-neutral",
  info: "badge-info",
} as const;

export type Tone = keyof typeof TONE_CLASS;

export function Badge({ tone, children }: { tone: Tone; children: ReactNode }) {
  return <span className={`badge ${TONE_CLASS[tone]}`}>{children}</span>;
}

export function DecisionBadge({ decision }: { decision: string }) {
  const tone: Tone =
    decision === "CLEAR" ? "success" :
    decision === "BLOCK" ? "danger" : "warning";
  return <Badge tone={tone}>{decisionLabel(decision)}</Badge>;
}

export function StatusDot({ status }: { status: string }) {
  const cls =
    status === "ok" ? "dot-success" :
    status === "degraded" ? "dot-warning" : "dot-danger";
  return <span className={`dot ${cls}`} role="img"
    aria-label={`${status} status`} />;
}

export function SeverityBadge({ severity }: { severity: string }) {
  const tone: Tone =
    severity === "critical" || severity === "high" ? "danger" :
    severity === "medium" ? "warning" : "neutral";
  return <Badge tone={tone}>{severity.toUpperCase()}</Badge>;
}

function formatDateTimeShort(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "—" : d.toLocaleString();
}

export function ConfidenceMeter({ value, label = "Confidence" }: { value: number; label?: string }) {
  const pct = Math.round(value * 100);
  const tone = riskTone(1 - value); // high confidence => calm colour
  const color = tone === "danger" ? "var(--c-danger)"
    : tone === "warning" ? "var(--c-warning)" : "var(--c-success)";
  return (
    <div>
      <div className="meter-label">
        <span>{label}</span>
        <span aria-hidden="true">{pct}%</span>
      </div>
      <div className="meter" role="meter" aria-valuemin={0} aria-valuemax={100}
        aria-valuenow={pct} aria-label={label}>
        <div style={{ width: `${pct}%`, background: color }} />
      </div>
    </div>
  );
}

export function RiskScore({ score }: { score: number }) {
  return (
    <span>
      <strong>{formatScore(score)}</strong>{" "}
      <span className="muted" style={{ fontSize: 12 }}>risk</span>
    </span>
  );
}

export function EmptyState({ message, hint }: { message: string; hint?: string }) {
  return (
    <div className="empty" role="status">
      <p>{message}</p>
      {hint && <p style={{ fontSize: 12.5, marginTop: 4 }}>{hint}</p>}
    </div>
  );
}

export function Loading({ label = "Loading…" }: { label?: string }) {
  return <div className="empty" role="status" aria-live="polite">{label}</div>;
}

export function ErrorBox({ error }: { error: { message: string; requestId?: string; retryAfter?: number } }) {
  return (
    <div className="error-box" role="alert">
      <strong>Unable to complete the request. </strong>
      {error.message}
      {error.retryAfter !== undefined && (
        <> Retry after approximately {error.retryAfter}s.</>
      )}
      {error.requestId && (
        <span className="err-id mono">Correlation ID: {error.requestId}</span>
      )}
    </div>
  );
}

export function SignalTable({ signals }: { signals: Signal[] }) {
  if (!signals.length) return <EmptyState message="No signals recorded for this result." />;
  return (
    <div className="table-wrap">
      <table className="data">
        <thead>
          <tr>
            <th scope="col">Signal</th><th scope="col">Value</th>
            <th scope="col">Weight</th><th scope="col">Source</th>
            <th scope="col">Explanation</th>
          </tr>
        </thead>
        <tbody>
          {signals.map((s, i) => (
            <tr key={`${s.name}-${i}`}>
              <td className="mono">{s.name}</td>
              <td>{formatScore(s.value)}</td>
              <td>{s.weight.toFixed(2)}</td>
              <td>{s.source || "—"}</td>
              <td>{s.reason || "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Full, explainable verification result panel used by all engines. */
export function ResultPanel({ result }: { result: EngineResult }) {
  return (
    <Card title="Verification result">
      <div className="card-grid grid-3 mb">
        <div>
          <p className="stat-label">Decision</p>
          <DecisionBadge decision={result.decision} />
        </div>
        <div>
          <p className="stat-label">Risk score</p>
          <RiskScore score={result.risk_score} />
        </div>
        <div>
          <ConfidenceMeter value={result.confidence} />
        </div>
      </div>
      <h2 style={{ fontSize: 13.5 }}>Why this decision</h2>
      <ul style={{ paddingLeft: 20, fontSize: 13.5 }}>
        {result.reasons.map((r, i) => <li key={i}>{r}</li>)}
      </ul>
      <div className="mt">
        <SignalTable signals={result.signals} />
      </div>
      <p className="muted mt" style={{ fontSize: 12 }}>
        Engine: <span className="mono">{result.engine}</span> · Model:{" "}
        <span className="mono">{result.model_version || "—"}</span> ·{" "}
        {result.processing_time_ms.toFixed(1)} ms ·{" "}
        {formatDateTimeShort(result.timestamp)}
      </p>
    </Card>
  );
}


