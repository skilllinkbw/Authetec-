/** Display formatting helpers. */

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, {
    year: "numeric", month: "short", day: "2-digit",
    hour: "2-digit", minute: "2-digit", second: "2-digit",
  });
}

export function formatScore(score: number | undefined | null): string {
  if (score === undefined || score === null || Number.isNaN(score)) return "—";
  return (score * 100).toFixed(1) + "%";
}

/** Risk tone for badges/meters. Never implies certainty beyond the score. */
export function riskTone(score: number): "success" | "warning" | "danger" {
  if (score >= 0.7) return "danger";
  if (score >= 0.3) return "warning";
  return "success";
}

/** Decision display label — engine decisions are authoritative; these
 * labels translate them into reviewer-friendly language. */
export function decisionLabel(decision: string): string {
  switch (decision) {
    case "CLEAR": return "Verified";
    case "REVIEW": return "Review required";
    case "BLOCK": return "Rejected";
    default: return decision;
  }
}

export function shortId(id: string | undefined, head = 10): string {
  if (!id) return "—";
  return id.length <= head ? id : id.slice(0, head) + "…";
}

export function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = String(reader.result);
      // strip data URL prefix; backend expects bare base64
      const comma = result.indexOf(",");
      resolve(comma >= 0 ? result.slice(comma + 1) : result);
    };
    reader.onerror = () => reject(new Error("Could not read the selected file."));
    reader.readAsDataURL(file);
  });
}

export function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}
