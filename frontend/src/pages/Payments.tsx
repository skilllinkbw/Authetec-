/**
 * Payment Fraud Detection console — scores a transaction through the
 * backend's rule/model pipeline and shows the explainable result.
 */
import { useState } from "react";
import { scorePayment } from "../lib/api/endpoints";
import { ApiError } from "../lib/api/client";
import { Card, ErrorBox, PageTitle, ResultPanel } from "../components/ui";
import type { EngineResult } from "../types/api";

export default function Payments() {
  const [form, setForm] = useState({
    transaction_id: "", amount: "", account_balance: "",
    channel: "card", timestamp: "",
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [result, setResult] = useState<EngineResult | null>(null);
  const [txId, setTxId] = useState("");

  function set<K extends keyof typeof form>(key: K, value: string) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setError(null); setResult(null);
    try {
      const amount = Number(form.amount);
      if (!form.transaction_id.trim() || Number.isNaN(amount) || amount < 0) {
        throw new ApiError(400, "client_validation",
          "A transaction ID and a non-negative amount are required.");
      }
      const payload: Record<string, unknown> = {
        transaction_id: form.transaction_id.trim(),
        amount,
        channel: form.channel,
      };
      if (form.account_balance) payload.account_balance = Number(form.account_balance);
      if (form.timestamp) payload.timestamp = form.timestamp;
      const res = await scorePayment(payload);
      setResult(res.result);
      setTxId(res.transaction_id);
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
        title="Payment Fraud Detection"
        subtitle={"Explainable transaction scoring: amount anomalies, velocity, " +
          "card freshness and channel risk, combined by the risk engine."}
      />

      <Card title="Score a transaction">
        <form onSubmit={submit}>
          <div className="card-grid grid-3">
            <label className="field">
              <span>Transaction ID</span>
              <input type="text" value={form.transaction_id} required
                aria-required="true"
                onChange={(e) => set("transaction_id", e.target.value)} />
            </label>
            <label className="field">
              <span>Amount</span>
              <input type="number" min="0" step="0.01" value={form.amount} required
                aria-required="true"
                onChange={(e) => set("amount", e.target.value)} />
            </label>
            <label className="field">
              <span>Account balance (optional)</span>
              <input type="number" min="0" step="0.01" value={form.account_balance}
                onChange={(e) => set("account_balance", e.target.value)} />
            </label>
            <label className="field">
              <span>Channel</span>
              <select value={form.channel}
                onChange={(e) => set("channel", e.target.value)}>
                <option value="card">Card</option>
                <option value="bank_transfer">Bank transfer</option>
                <option value="mobile_money">Mobile money</option>
                <option value="wallet">Wallet</option>
                <option value="crypto">Crypto</option>
              </select>
            </label>
            <label className="field">
              <span>Timestamp (optional, ISO 8601)</span>
              <input type="text" placeholder="2026-08-30T14:00:00"
                value={form.timestamp}
                onChange={(e) => set("timestamp", e.target.value)} />
            </label>
          </div>
          <button className="btn" type="submit" disabled={busy}>
            {busy ? "Scoring…" : "Score transaction"}
          </button>
        </form>
      </Card>

      {error && <div className="mt"><ErrorBox error={error} /></div>}
      {result && (
        <div className="mt">
          <p className="muted" style={{ fontSize: 13 }}>
            Transaction <span className="mono">{txId}</span>
          </p>
          <ResultPanel result={result} />
        </div>
      )}
    </>
  );
}
