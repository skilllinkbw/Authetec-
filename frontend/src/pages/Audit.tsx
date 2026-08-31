/**
 * Audit Center — append-oriented audit trail with hash-chain integrity
 * verification. Entries are tenant-scoped by the backend.
 */
import { listAudit, auditIntegrity } from "../lib/api/endpoints";
import { useApi } from "../hooks/useApi";
import { formatDateTime } from "../lib/format";
import {
  Badge, Card, EmptyState, ErrorBox, Loading, PageTitle,
} from "../components/ui";

export default function Audit() {
  const list = useApi(() => listAudit(100), []);
  const integrity = useApi(auditIntegrity, []);

  return (
    <>
      <PageTitle
        title="Audit Center"
        subtitle="Every security-relevant action, append-only and hash-chained."
      />

      <div className="mb">
        {integrity.loading ? null :
          integrity.error ? <ErrorBox error={integrity.error} /> :
            integrity.data && (
              <div className={integrity.data.valid ? "callout" : "callout warn"}
                role="status">
                {integrity.data.valid
                  ? `Audit hash chain integrity verified — ${integrity.data.entries_checked} entr${integrity.data.entries_checked === 1 ? "y" : "ies"} checked.`
                  : "Audit hash chain verification FAILED — entries may have been tampered with."}
              </div>
            )}
      </div>

      <Card title="Audit entries">
        {list.loading ? <Loading /> :
          list.error ? <ErrorBox error={list.error} /> :
            list.data && list.data.count > 0 ? (
              <div className="table-wrap">
                <table className="data">
                  <thead>
                    <tr>
                      <th scope="col">Timestamp</th><th scope="col">Event</th>
                      <th scope="col">Actor</th><th scope="col">Entity</th>
                      <th scope="col">Result</th><th scope="col">Correlation ID</th>
                    </tr>
                  </thead>
                  <tbody>
                    {list.data.entries.map((e) => (
                      <tr key={e.event_id}>
                        <td>{formatDateTime(e.timestamp)}</td>
                        <td className="mono">{e.event_type}</td>
                        <td>{e.actor_id}</td>
                        <td>
                          {e.resource_type
                            ? `${e.resource_type}:${shortIdLocal(e.resource_id)}`
                            : "—"}
                        </td>
                        <td><Badge tone={e.result === "clear" || e.result === "success"
                          ? "success" : e.result === "block" ? "danger" : "warning"}>
                          {e.result}</Badge></td>
                        <td className="mono">{e.correlation_id.slice(0, 12)}…</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <EmptyState message="No audit entries for this workspace yet."
                hint="Verification, alert and scoring actions are recorded automatically." />
            )}
      </Card>
    </>
  );
}

function shortIdLocal(id: string): string {
  return id && id.length > 10 ? id.slice(0, 10) + "…" : (id || "—");
}
