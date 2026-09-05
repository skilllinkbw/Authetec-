/**
 * Document Verification workspace — upload a document (PNG/JPEG/TIFF/PDF)
 * and receive the engine's explainable result. The pipeline and signals
 * come from the backend; the UI adds no interpretation of its own.
 */
import { useState } from "react";
import { verifyDocument } from "../lib/api/endpoints";
import { ApiError } from "../lib/api/client";
import { formatBytes, shortId } from "../lib/format";
import {
  Card, ErrorBox, PageTitle, ResultPanel,
} from "../components/ui";
import type { EngineResult } from "../types/api";

const DOC_TYPES = [
  { value: "", label: "Any / unspecified" },
  { value: "national_id", label: "National ID" },
  { value: "passport", label: "Passport" },
  { value: "drivers_licence", label: "Driver's licence" },
  { value: "certificate", label: "Certificate" },
  { value: "invoice", label: "Invoice" },
  { value: "contract", label: "Contract" },
];

export default function Documents() {
  const [file, setFile] = useState<File | null>(null);
  const [expectedType, setExpectedType] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [result, setResult] = useState<EngineResult | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!file) return;
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      setResult(await verifyDocument(file, expectedType));
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
        title="Document Verification"
        subtitle={"Uploads are validated by file signature, classified, and analysed " +
          "for text-layer, metadata and re-compression anomalies."}
      />

      <Card title="Submit a document">
        <form onSubmit={submit}>
          <label className="field">
            <span>Document (PNG, JPEG, TIFF or PDF · max 20 MB)</span>
            <input type="file" accept=".png,.jpg,.jpeg,.tif,.tiff,.pdf"
              onChange={(e) => { setFile(e.target.files?.[0] ?? null); setResult(null); }}
              aria-required="true" />
          </label>
          {file && (
            <p className="muted" style={{ fontSize: 12.5, marginBottom: 12 }}>
              {file.name} · {formatBytes(file.size)}
            </p>
          )}
          <label className="field">
            <span>Declared document type (optional)</span>
            <select value={expectedType}
              onChange={(e) => setExpectedType(e.target.value)}>
              {DOC_TYPES.map((t) => (
                <option key={t.value} value={t.value}>{t.label}</option>
              ))}
            </select>
          </label>
          <button className="btn" type="submit" disabled={!file || busy}>
            {busy ? "Analysing…" : "Verify document"}
          </button>
        </form>
      </Card>

      {error && <div className="mt"><ErrorBox error={error} /></div>}

      {result && (
        <div className="mt">
          <ResultPanel result={result} />
          <Card title="Evidence & integrity" className="mt">
            <table className="data">
              <tbody>
                <tr>
                  <th scope="row">Content hash (SHA-256)</th>
                  <td className="mono">{String(result.extra?.sha256 ?? "—")}</td>
                </tr>
                <tr>
                  <th scope="row">Evidence reference</th>
                  <td className="mono">{shortId(String(result.extra?.stored_evidence_id ?? ""), 14)}</td>
                </tr>
                <tr>
                  <th scope="row">Classification</th>
                  <td className="mono">
                    {JSON.stringify(result.extra?.classification ?? "—")}
                  </td>
                </tr>
              </tbody>
            </table>
          </Card>
        </div>
      )}
    </>
  );
}
