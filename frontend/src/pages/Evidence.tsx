/**
 * Evidence Center — registry of immutable evidence references produced by
 * verification flows. Content hashes are recorded by the engines; raw
 * artefacts stay in object storage, referenced by URI.
 */
import { listEvidence } from "../lib/api/endpoints";
import { useApi } from "../hooks/useApi";
import { formatDateTime } from "../lib/format";
import {
  Card, EmptyState, ErrorBox, Loading, PageTitle,
} from "../components/ui";

export default function Evidence() {
  const list = useApi(() => listEvidence(100), []);

  return (
    <>
      <PageTitle
        title="Evidence Center"
        subtitle="Immutable references to verification artefacts for your workspace."
      />

      <Card title="Evidence registry">
        {list.loading ? <Loading /> :
          list.error ? <ErrorBox error={list.error} /> :
            list.data && list.data.count > 0 ? (
              <div className="table-wrap">
                <table className="data">
                  <thead>
                    <tr>
                      <th scope="col">Evidence ID</th><th scope="col">Purpose</th>
                      <th scope="col">Type</th><th scope="col">Storage reference</th>
                      <th scope="col">Recorded</th>
                    </tr>
                  </thead>
                  <tbody>
                    {list.data.evidence.map((e) => (
                    <tr key={e.evidence_id}>
                      <td className="mono">{e.evidence_id.slice(0, 12)}…</td>
                      <td>{e.purpose || "—"}</td>
                      <td>{e.content_type || "—"}</td>
                      <td className="mono">{e.storage_uri}</td>
                      <td>{formatDateTime(e.created_at)}</td>
                    </tr>
                  ))}
                  </tbody>
                </table>
                <p className="muted mt" style={{ fontSize: 12 }}>
                  Content hashes (SHA-256) are recorded in evidence metadata at
                  capture time. Cryptographic integrity re-verification of
                  stored objects is a planned capability and is not yet claimed.
                </p>
              </div>
            ) : (
              <EmptyState message="No data available."
                hint="Evidence references appear after running document or signature verification." />
            )}
      </Card>
    </>
  );
}
