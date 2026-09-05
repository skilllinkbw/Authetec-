"""Human-readable biometric benchmark report generation.

Builds ``BIOMETRIC_BENCHMARK_REPORT.md`` from the machine-readable results
dict emitted by the runner.  The report never invents numbers: every metric
is read from the results blob that the benchmarks calculated.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

REPORT_FILENAME = "BIOMETRIC_BENCHMARK_REPORT.md"


def _fmt(value: Any, digits: int = 4) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def _data_source_note(results: Dict[str, Any]) -> str:
    ds = (results.get("dataset") or {}).get("name", "")
    if ds == "synthetic-fixture":
        return ("SYNTHETIC DATA ONLY - these numbers exercise the pipeline; "
                "they are NOT real-world biometric evidence and must not be "
                "reported as such.")
    return "Reported from the dataset recorded in the manifest."


def generate_report(results: Dict[str, Any], *, out_dir: Path) -> Path:
    """Write BIOMETRIC_BENCHMARK_REPORT.md; returns its path."""
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / REPORT_FILENAME

    env = results.get("environment", {})
    ds = results.get("dataset") or {}
    ver = results.get("verification") or {}
    tha = results.get("threshold_analysis") or {}
    pad = results.get("pad") or {}
    perf = results.get("performance") or {}
    sec = results.get("security") or {}
    gates = results.get("gates") or {}
    integ = results.get("model_integrity") or {}

    lines: list[str] = []
    a = lines.append
    a("# AUTHeTEC PHASE 2 BIOMETRIC VALIDATION REPORT")
    a("")
    a(f"> {_data_source_note(results)}")
    a("")

    a("## 1. Executive Summary")
    a("")
    a(f"- Verification ROC-AUC: {_fmt(ver.get('rocauc'))}")
    a(f"- Verification EER: {_fmt(ver.get('eer'))} "
      f"(threshold {_fmt(ver.get('eer_threshold'))})")
    a(f"- Verification F1 @ selected threshold: {_fmt(ver.get('f1'))}")
    a(f"- PAD ACER: {_fmt(pad.get('acer'))}")
    a(f"- PAD APCER: {_fmt(pad.get('apcer'))} / "
      f"BPCER: {_fmt(pad.get('bpcer'))}")
    a(f"- End-to-end p95 latency: "
      f"{_fmt((perf.get('end_to_end') or {}).get('p95_ms'))} ms")
    a(f"- Regression gates: "
      f"{'PASS' if gates.get('passed') else 'SEE GATES SECTION'}")
    a("")

    a("## 2. System Under Test")
    a("")
    a(f"- Provider: "
      f"`{results.get('config', {}).get('provider', 'unknown')}`")
    a(f"- Verification threshold: "
      f"{_fmt(results.get('config', {}).get('threshold'))}")
    a(f"- Git commit: `{env.get('git_commit', 'unknown')}`")
    a(f"- Timestamp (UTC): {env.get('timestamp_utc', 'unknown')}")
    a("")

    a("## 3. Model / Provider Configuration")
    a("")
    a(f"- Provider label: "
      f"`{results.get('config', {}).get('provider', 'unknown')}`")
    a("- Embedder / detector / PAD implementations are injected per "
      "`AUTHETEC_FACE_PROVIDER` / `AUTHETEC_PAD_PROVIDER`; nothing in the "
      "benchmark hard-codes a provider.")
    a("")
    a("### Model integrity")
    a("")
    if integ.get("results"):
        a("| Model | Status | Expected SHA-256 |")
        a("|---|---|---|")
        for r in integ["results"]:
            a(f"| {r['model_key']} | {r['status']} | "
              f"`{r['expected_sha256'][:16]}..` |")
    else:
        a("No pinned models found (`models/model_pins.json` empty/missing).")
    a("")

    a("## 4. Dataset")
    a("")
    a(f"- Name: {ds.get('name', 'n/a')} (version {ds.get('version', 'n/a')})")
    a(f"- Source: {ds.get('source', 'n/a')}")
    a(f"- License: {ds.get('license', 'n/a')}")
    a(f"- Subjects: {ds.get('n_subjects', 'n/a')}")
    a(f"- Bona-fide samples: {ds.get('n_bonafide', 'n/a')}")
    a(f"- Attack samples: {ds.get('n_attack', 'n/a')}")
    a(f"- Attack types: {(ds.get('attack_types') or {})}")
    a("")

    a("## 5. Dataset Integrity")
    a("")
    issues = ds.get("integrity_issues") or []
    if issues:
        a("**Issues found:**")
        for i in issues:
            a(f"- {i}")
    else:
        a("No integrity issues recorded.")
    a("")
    a("## 6. Face Verification Results")
    a("- TP/TN/FP/FN: "
      f"{ver.get('tp')}/{ver.get('tn')}/{ver.get('fp')}/{ver.get('fn')}")
    a(f"- FAR: {_fmt(ver.get('far'))}")
    a(f"- FRR: {_fmt(ver.get('frr'))}")
    a(f"- Precision: {_fmt(ver.get('precision'))} / "
      f"Recall: {_fmt(ver.get('recall'))} / F1: {_fmt(ver.get('f1'))}")
    a(f"- Accuracy: {_fmt(ver.get('accuracy'))}")
    a(f"- ROC-AUC: {_fmt(ver.get('rocauc'))}")
    a(f"- EER: {_fmt(ver.get('eer'))} at threshold "
      f"{_fmt(ver.get('eer_threshold'))}")
    a(f"- Operating threshold: {_fmt(tha.get('selected_threshold'))} "
      f"(FAR {_fmt(tha.get('selected_far'))}, "
      f"FRR {_fmt(tha.get('selected_frr'))})")
    a("")

    a("## 7. Threshold Analysis")
    a("")
    pts = tha.get("points", [])
    a("| Threshold | FAR | FRR | Precision | Recall | F1 |")
    a("|---|---|---|---|---|---|")
    for p in pts[:25]:
        a(f"| {_fmt(p['threshold'], 3)} | {_fmt(p['far'], 3)} | "
          f"{_fmt(p['frr'], 3)} | {_fmt(p['precision'], 3)} | "
          f"{_fmt(p['recall'], 3)} | {_fmt(p['f1'], 3)} |")
    a("")
    a(f"- ROC-AUC: {_fmt(tha.get('rocauc'))} | "
      f"EER: {_fmt(tha.get('eer'))} at {_fmt(tha.get('eer_threshold'))}")
    a("")

    a("## 8. PAD / Liveness Results")
    a("- n bona-fide / n attacks: "
      f"{pad.get('n_bonafide')} / {pad.get('n_attack')}")
    a(f"- APCER: {_fmt(pad.get('apcer'))}")
    a(f"- BPCER: {_fmt(pad.get('bpcer'))}")
    a(f"- ACER: {_fmt(pad.get('acer'))}")
    a(f"- Attack acceptance rate: {_fmt(pad.get('attack_accept_rate'))}")
    a(f"- Bona-fide acceptance rate: "
      f"{_fmt(pad.get('bonafide_accept_rate'))}")
    for atype, d in (pad.get("attack_specific") or {}).items():
        a(f"- Attack type `{atype}`: n={d.get('n')}, "
          f"accept_rate={_fmt(d.get('accept_rate'))}")
    a("")

    a("## 9. Document-to-Selfie Results")
    a("Not measured in this run - requires a dedicated labelled "
      "document-to-selfie dataset (separate protocol).")
    a("")

    a("## 10. Robustness Results")
    a("Not measured in this run - requires a labelled robustness dataset "
      "(lighting/pose/blur/resolution dimensions).")
    a("")

    a("## 11. Performance Results")
    a("")
    a("| Stage | n | mean ms | p50 | p95 | p99 |")
    a("|---|---|---|---|---|---|")
    for key in ("detection", "alignment", "embedding", "pad", "end_to_end"):
        s = (perf.get(key) or {})
        if s.get("stage"):
            a(f"| {key} | {s.get('n')} | {_fmt(s.get('mean_ms'), 1)} | "
              f"{_fmt(s.get('p50_ms'), 1)} | {_fmt(s.get('p95_ms'), 1)} | "
              f"{_fmt(s.get('p99_ms'), 1)} |")
    a("")
    a(f"- Throughput: {_fmt(perf.get('throughput_per_sec'), 1)} samples/s")
    a("")

    a("## 12. Security Results")
    a("")
    a(f"- Malformed-input rejection verified: "
      f"{sec.get('malformed_rejected', 'n/a')}")
    a(f"- Provider fail-closed behavior: "
      f"{sec.get('provider_fail_closed', 'n/a')}")
    a("- No raw biometric images or embeddings are stored in any report or "
      "log produced by this benchmark.")
    a("")

    a("## 13. Open-Source Baseline Comparison")
    a("Not performed in this run - requires an approved baseline stack "
      "matched to the same dataset/protocol.")
    a("")

    a("## 14. Reproducibility Information")
    a("")
    a(f"- Git commit: `{env.get('git_commit', 'unknown')}`")
    a(f"- Python: {env.get('python_version', 'n/a')}")
    a(f"- Platform: {env.get('platform', 'n/a')}")
    a(f"- CPU: {env.get('processor', 'n/a')} x {env.get('cpu_count', 'n/a')}")
    a(f"- RAM: {env.get('ram_total_gb', 'n/a')} GB")
    a(f"- Packages: {env.get('packages', {})}")
    a(f"- Dataset seed: "
      f"{results.get('config', {}).get('dataset_seed', 'n/a')}")
    a("")

    a("## 15. Limitations")
    a("")
    a(f"- {_data_source_note(results)}")
    a("- PAD calibration for the native engine is synthetic pending a "
      "labelled presentation-attack dataset (ISO/IEC 30107-3 protocol).")
    a("- No demographic fairness evaluation performed.")
    a("- No GPU / Android / multi-node runtime validation performed.")
    a("")

    a("## 16. Production Readiness")
    a("")
    if ds.get("name") == "synthetic-fixture":
        a("**NOT READY** - this run used synthetic data only. Real-world "
          "validation requires a lawful labelled dataset; the infrastructure "
          "to run it is in place (see Sections 4-8).")
    else:
        a("Evaluate against the recorded dataset, the configured regression "
          "gates, and the deployment's security review.  An automated "
          "benchmark alone cannot certify production readiness - the "
          "dataset's representativeness, PAD protocol, and threat model "
          "must be weighed together.")
    a("")

    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path
