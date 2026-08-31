/**
 * Signature Verification workspace (Signature Guard).
 * Enroll a reference signature, then verify submissions against it.
 * Mismatch alerts for monitored owners are raised server-side.
 */
import { useState } from "react";
import { enrollSignature, verifySignature } from "../lib/api/endpoints";
import { ApiError } from "../lib/api/client";
import { fileToBase64, formatScore, shortId } from "../lib/format";
import {
  Badge, Card, ConfidenceMeter, ErrorBox, PageTitle, SignalTable,
} from "../components/ui";
import type { EngineResult, SignatureResult } from "../types/api";

export default function Signatures() {
  return (
    <>
      <PageTitle
        title="Signature Verification"
        subtitle={"Shape-based similarity against enrolled reference signatures. " +
          "A similarity score is a signal — not legal proof of authorship."}
      />
      <div className="card-grid grid-2">
        <EnrollPanel />
        <VerifyPanel />
      </div>
    </>
  );
}

function EnrollPanel() {
  const [ownerId, setOwnerId] = useState("");
  const [label, setLabel] = useState("");
  const [monitored, setMonitored] = useState(true);
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [enrolled, setEnrolled] = useState<SignatureResult | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!file || !ownerId.trim()) return;
    setBusy(true); setError(null); setEnrolled(null);
    try {
      const imageB64 = await fileToBase64(file);
      setEnrolled(await enrollSignature({
        owner_id: ownerId.trim(), label: label.trim(), monitored, image_b64: imageB64,
      }));
    } catch (err) {
      setError(err instanceof ApiError ? err
        : new ApiError(0, "unknown_error", "An unexpected error occurred."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card title="1 · Enroll reference signature">
      <form onSubmit={submit}>
        <label className="field">
          <span>Owner identifier</span>
          <input type="text" value={ownerId} required aria-required="true"
            onChange={(e) => setOwnerId(e.target.value)} />
        </label>
        <label className="field">
          <span>Label (e.g. passport, account mandate)</span>
          <input type="text" value={label}
            onChange={(e) => setLabel(e.target.value)} />
        </label>
        <label className="field" style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <input type="checkbox" checked={monitored}
            onChange={(e) => setMonitored(e.target.checked)} />
          <span style={{ margin: 0 }}>Monitor this owner (Signature Guard alerts on mismatch)</span>
        </label>
        <label className="field">
          <span>Reference signature image (PNG/JPEG)</span>
          <input type="file" accept=".png,.jpg,.jpeg" aria-required="true"
            onChange={(e) => { setFile(e.target.files?.[0] ?? null); setEnrolled(null); }} />
        </label>
        <button className="btn" type="submit" disabled={!file || !ownerId.trim() || busy}>
          {busy ? "Enrolling…" : "Enroll signature"}
        </button>
      </form>

      {error && <div className="mt"><ErrorBox error={error} /></div>}
      {enrolled && enrolled.result.decision === "CLEAR" && (
        <div className="callout mt" role="status">
          Reference enrolled. Signature ID:{" "}
          <span className="mono">{shortId(enrolled.signature_id, 16)}</span> — copy
          this ID for verification.
        </div>
      )}
      {enrolled && enrolled.result.decision !== "CLEAR" && (
        <div className="mt"><ErrorBox error={{
          message: enrolled.result.reasons[0] ?? "Enrollment failed.",
        }} /></div>
      )}
    </Card>
  );
}

function VerifyPanel() {
  const [ownerId, setOwnerId] = useState("");
  const [referenceId, setReferenceId] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [result, setResult] = useState<EngineResult | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!file || !ownerId.trim()) return;
    setBusy(true); setError(null); setResult(null);
    try {
      const imageB64 = await fileToBase64(file);
      const res = await verifySignature({
        owner_id: ownerId.trim(),
        reference_id: referenceId.trim() || undefined,
        image_b64: imageB64,
      });
      setResult(res.result);
    } catch (err) {
      setError(err instanceof ApiError ? err
        : new ApiError(0, "unknown_error", "An unexpected error occurred."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card title="2 · Verify a signature">
      <form onSubmit={submit}>
        <label className="field">
          <span>Owner identifier</span>
          <input type="text" value={ownerId} required aria-required="true"
            onChange={(e) => setOwnerId(e.target.value)} />
        </label>
        <label className="field">
          <span>Reference signature ID (optional — best match if omitted)</span>
          <input type="text" value={referenceId}
            onChange={(e) => setReferenceId(e.target.value)} />
        </label>
        <label className="field">
          <span>Signature image to verify (PNG/JPEG)</span>
          <input type="file" accept=".png,.jpg,.jpeg" aria-required="true"
            onChange={(e) => { setFile(e.target.files?.[0] ?? null); setResult(null); }} />
        </label>
        <button className="btn" type="submit" disabled={!file || !ownerId.trim() || busy}>
          {busy ? "Verifying…" : "Verify signature"}
        </button>
      </form>

      {error && <div className="mt"><ErrorBox error={error} /></div>}

      {result && (
        <div className="mt">
          <div className="card-grid grid-3 mb">
            <div>
              <p className="stat-label">Decision</p>
              <Badge tone={result.decision === "CLEAR" ? "success"
                : result.decision === "BLOCK" ? "danger" : "warning"}>
                {result.decision === "CLEAR" ? "MATCH"
                  : result.decision === "BLOCK" ? "LIKELY FORGERY" : "REVIEW"}
              </Badge>
            </div>
            <div>
              <p className="stat-label">Match score</p>
              <p className="stat-value" style={{ fontSize: 20 }}>
                {formatScore(result.signals[0]?.value ?? 0)}
              </p>
            </div>
            <div>
              <ConfidenceMeter value={result.confidence} />
            </div>
          </div>
          <h2 style={{ fontSize: 13.5 }}>Why this decision</h2>
          <ul style={{ paddingLeft: 20, fontSize: 13.5 }}>
            {result.reasons.map((r, i) => <li key={i}>{r}</li>)}
          </ul>
          <div className="mt"><SignalTable signals={result.signals} /></div>
        </div>
      )}
    </Card>
  );
}
