/**
 * Alert Center — filter, acknowledge and resolve alerts. Every action is
 * audited server-side; the UI reflects backend state only.
 */
import { useState } from "react";
import {
  acknowledgeAlert, listAlerts, resolveAlert,
} from "../lib/api/endpoints";
import { ApiError } from "../lib/api/client";
import { formatDateTime, shortId } from "../lib/format";
import { useApi } from "../hooks/useApi";
import {
  Badge, Card, EmptyState, ErrorBox, Loading, PageTitle, SeverityBadge,
} from "../components/ui";
import type { Alert } from "../types/api";

const STATUS_FILTERS = ["", "OPEN", "ACKNOWLEDGED", "RESOLVED"];

export default function Alerts() {
  const [statusFilter, setStatusFilter] = useState("");
  const list = useApi(() => listAlerts(statusFilter || undefined), [statusFilter]);
  const [actionError, setActionError] = useState<ApiError | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  async function act(alert: Alert, action: "acknowledge" | "resolve") {
    setBusyId(alert.alert_id);
    setActionError(null);
    try {
      await (action === "acknowledge"
        ? acknowledgeAlert(alert.alert_id)
        : resolveAlert(alert.alert_id));
      list.reload();
    } catch (err) {
      setActionError(err instanceof ApiError ? err
        : new ApiError(0, "unknown_error", "An unexpected error occurred."));
    } finally {
      setBusyId(null);
    }
  }

  return (
    <>
      <PageTitle
        title="Alert Center"
        subtitle="Suspicious events raised across verification and fraud engines."
      />

      <Card title="Alerts">
        <label className="field" style={{ maxWidth: 240 }}>
          <span>Status filter</span>
          <select value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}>
            {STATUS_FILTERS.map((s) => (
              <option key={s} value={s}>{s || "All statuses"}</option>
            ))}
          </select>
        </label>

        {list.loading ? <Loading /> :
          list.error ? <ErrorBox error={list.error} /> :
            actionError && <ErrorBox error={actionError} />}

        {!list.loading && list.data && (
          list.data.count === 0 ? (
            <EmptyState message="No alerts match this filter."
              hint="Alerts appear when engines flag suspicious activity." />
          ) : (
            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr>
                    <th scope="col">Severity</th><th scope="col">Type</th>
                    <th scope="col">Risk</th><th scope="col">Message</th>
                    <th scope="col">Status</th><th scope="col">Created</th>
                    <th scope="col">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {list.data.alerts.map((a) => (
                    <tr key={a.alert_id}>
                      <td><SeverityBadge severity={a.severity} /></td>
                      <td className="mono">{a.type}</td>
                      <td>{(a.risk_score * 100).toFixed(0)}%</td>
                      <td>{a.message}</td>
                      <td><Badge tone={a.status === "OPEN" ? "warning"
                        : a.status === "RESOLVED" ? "success" : "info"}>
                        {a.status}</Badge></td>
                      <td>{formatDateTime(a.created_at)}</td>
                      <td>
                        {a.status === "OPEN" && (
                          <button className="btn btn-secondary btn-sm"
                            disabled={busyId === a.alert_id}
                            onClick={() => act(a, "acknowledge")}>
                            Acknowledge
                          </button>
                        )}
                        {a.status !== "RESOLVED" && (
                          <button className="btn btn-sm" style={{ marginLeft: 6 }}
                            disabled={busyId === a.alert_id}
                            onClick={() => act(a, "resolve")}>
                            Resolve
                          </button>
                        )}
                        <span className="muted mono" style={{ display: "block", marginTop: 4, fontSize: 11 }}>
                          {shortId(a.alert_id, 8)}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )
        )}
      </Card>
    </>
  );
}
