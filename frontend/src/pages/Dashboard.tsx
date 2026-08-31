/**
 * Dashboard — live system health, alert snapshot and recent activity.
 * Metrics the backend does not aggregate yet are shown honestly as
 * "No data available" — the platform never fabricates statistics.
 */
import { Link } from "react-router-dom";
import { getHealth, listAlerts, listAudit } from "../lib/api/endpoints";
import { useApi } from "../hooks/useApi";
import { formatDateTime, shortId } from "../lib/format";
import {
  Badge, Card, EmptyState, ErrorBox, Loading, PageTitle, SeverityBadge, StatusDot,
} from "../components/ui";

export default function Dashboard() {
  const health = useApi(getHealth, []);
  const alerts = useApi(() => listAlerts(), []);
  const audit = useApi(() => listAudit(8), []);

  const openAlerts = alerts.data?.alerts.filter((a) => a.status === "OPEN") ?? [];
  const highRisk = alerts.data?.alerts.filter(
    (a) => (a.severity === "high" || a.severity === "critical") && a.status !== "RESOLVED") ?? [];

  return (
    <>
      <PageTitle
        title="Dashboard"
        subtitle="Live platform status and activity for your workspace."
      />

      {health.error && <ErrorBox error={health.error} />}

      <section className="card-grid grid-3 mb" aria-label="Workspace summary">
        <Card title="Open alerts">
          {alerts.loading ? <Loading label="Loading alerts…" /> : (
            <p className="stat-value">{alerts.data ? openAlerts.length : "—"}</p>
          )}
          <p className="stat-label">
            {highRisk.length > 0
              ? `${highRisk.length} high-severity need attention`
              : "No high-severity alerts pending"}
          </p>
        </Card>
        <Card title="Verification volume">
          <EmptyState message="No data available"
            hint="Aggregate verification counters require analytics persistence (planned)." />
        </Card>
        <Card title="Model status">
          {health.data ? (
            (() => {
              const reg = health.data.components.find((c) => c.name === "model_registry");
              return (
                <>
                  <p className="stat-value" style={{ fontSize: 18 }}>
                    {String((reg?.detail as Record<string, unknown>)?.count ?? 0)} registered
                  </p>
                  <p className="stat-label">Deployed production models require
                    registry promotion — see Developers → module status.</p>
                </>
              );
            })()
          ) : <EmptyState message="No data available" />}
        </Card>
      </section>

      <div className="card-grid grid-2">
        <Card title="System health">
          {health.loading ? <Loading /> :
            health.error ? <EmptyState message="API status unavailable" /> : (
              <table className="data">
                <thead>
                  <tr><th scope="col">Component</th><th scope="col">Status</th></tr>
                </thead>
                <tbody>
                  {health.data!.components.map((c) => (
                    <tr key={c.name}>
                      <td>{c.name}</td>
                      <td><StatusDot status={c.status} /> {c.status}</td>
                    </tr>
                  ))}
                  <tr>
                    <td>platform</td>
                    <td className="mono">v{health.data!.version} · {health.data!.environment}</td>
                  </tr>
                </tbody>
              </table>
            )}
        </Card>

        <Card title="Recent activity">
          {audit.loading ? <Loading /> :
            audit.error ? <ErrorBox error={audit.error} /> :
              audit.data && audit.data.count > 0 ? (
                <table className="data">
                  <thead>
                    <tr><th scope="col">Event</th><th scope="col">Result</th><th scope="col">Time</th></tr>
                  </thead>
                  <tbody>
                    {audit.data.entries.map((e) => (
                      <tr key={e.event_id}>
                        <td className="mono">{e.event_type}</td>
                        <td><Badge tone={e.result === "clear" || e.result === "success"
                          ? "success" : e.result === "block" ? "danger" : "warning"}>
                          {e.result}</Badge></td>
                        <td>{formatDateTime(e.timestamp)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <EmptyState message="No activity recorded yet for this workspace."
                  hint="Verification and alert actions will appear here." />
              )}
        </Card>
      </div>

      <div className="mt">
        <Card title="Alerts needing attention">
          {alerts.loading ? <Loading /> :
            alerts.error ? <ErrorBox error={alerts.error} /> :
              openAlerts.length === 0 ? (
                <EmptyState message="No open alerts." hint="All clear in this workspace." />
              ) : (
                <table className="data">
                  <thead>
                    <tr>
                      <th scope="col">Severity</th><th scope="col">Type</th>
                      <th scope="col">Message</th><th scope="col">ID</th>
                    </tr>
                  </thead>
                  <tbody>
                    {openAlerts.slice(0, 5).map((a) => (
                      <tr key={a.alert_id}>
                        <td><SeverityBadge severity={a.severity} /></td>
                        <td className="mono">{a.type}</td>
                        <td>{a.message}</td>
                        <td className="mono">{shortId(a.alert_id)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
          <p className="mt" style={{ fontSize: 13 }}>
            <Link to="/alerts">Open the Alert Center →</Link>
          </p>
        </Card>
      </div>
    </>
  );
}
