/**
 * Social Trust console — scores a social/consumer profile through the
 * backend's explainable rule engine. Shows the result with the same
 * ResultPanel used by all verification engines.
 */
import { useState } from "react";
import { scoreSocial } from "../lib/api/endpoints";
import { ApiError } from "../lib/api/client";
import { Card, ErrorBox, PageTitle, ResultPanel } from "../components/ui";
import type { EngineResult } from "../types/api";

export default function Social() {
  const [form, setForm] = useState({
    profile_id: "", username: "", account_age_days: "",
    email_verified: "false", phone_verified: "false",
    post_frequency_per_day: "", following_count: "", follower_count: "",
    suspension_history_count: "0",
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [result, setResult] = useState<EngineResult | null>(null);
  const [profileId, setProfileId] = useState("");

  function set<K extends keyof typeof form>(key: K, value: string) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  function num(value: string): number | undefined {
    const n = Number(value);
    return Number.isNaN(n) ? undefined : n;
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setError(null); setResult(null);
    try {
      const payload: Record<string, unknown> = {
        profile_id: form.profile_id.trim(),
        username: form.username.trim(),
        email_verified: form.email_verified === "true",
        phone_verified: form.phone_verified === "true",
        suspension_history_count: num(form.suspension_history_count) ?? 0,
      };
      if (num(form.account_age_days) !== undefined) payload.account_age_days = num(form.account_age_days);
      if (num(form.post_frequency_per_day) !== undefined) payload.post_frequency_per_day = num(form.post_frequency_per_day);
      if (num(form.following_count) !== undefined) payload.following_count = num(form.following_count);
      if (num(form.follower_count) !== undefined) payload.follower_count = num(form.follower_count);
      const res = await scoreSocial(payload);
      setResult(res.result);
      setProfileId(res.profile_id);
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
        title="Social Trust"
        subtitle="Explainable profile risk scoring. Protected attributes are never used; every decision is backed by named signals."
      />

      <Card title="Score a profile">
        <form onSubmit={submit}>
          <div className="card-grid grid-3">
            <label className="field">
              <span>Profile ID</span>
              <input type="text" value={form.profile_id} onChange={(e) => set("profile_id", e.target.value)} />
            </label>
            <label className="field">
              <span>Username</span>
              <input type="text" value={form.username} onChange={(e) => set("username", e.target.value)} />
            </label>
            <label className="field">
              <span>Account age (days)</span>
              <input type="number" min="0" step="0.1" value={form.account_age_days}
                onChange={(e) => set("account_age_days", e.target.value)} />
            </label>
            <label className="field">
              <span>Email verified</span>
              <select value={form.email_verified}
                onChange={(e) => set("email_verified", e.target.value)}>
                <option value="false">No</option>
                <option value="true">Yes</option>
              </select>
            </label>
            <label className="field">
              <span>Phone verified</span>
              <select value={form.phone_verified}
                onChange={(e) => set("phone_verified", e.target.value)}>
                <option value="false">No</option>
                <option value="true">Yes</option>
              </select>
            </label>
            <label className="field">
              <span>Posts per day</span>
              <input type="number" min="0" step="0.1" value={form.post_frequency_per_day}
                onChange={(e) => set("post_frequency_per_day", e.target.value)} />
            </label>
            <label className="field">
              <span>Following</span>
              <input type="number" min="0" value={form.following_count}
                onChange={(e) => set("following_count", e.target.value)} />
            </label>
            <label className="field">
              <span>Followers</span>
              <input type="number" min="0" value={form.follower_count}
                onChange={(e) => set("follower_count", e.target.value)} />
            </label>
            <label className="field">
              <span>Prior suspensions</span>
              <input type="number" min="0" value={form.suspension_history_count}
                onChange={(e) => set("suspension_history_count", e.target.value)} />
            </label>
          </div>
          <button className="btn" type="submit" disabled={busy}>
            {busy ? "Scoring…" : "Score profile"}
          </button>
        </form>
      </Card>

      {error && <div className="mt"><ErrorBox error={error} /></div>}
      {result && (
        <div className="mt">
          <p className="muted" style={{ fontSize: 13 }}>
            Profile <span className="mono">{profileId || "(unnamed)"}</span>
          </p>
          <ResultPanel result={result} />
        </div>
      )}
    </>
  );
}