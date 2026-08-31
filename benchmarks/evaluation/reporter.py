"""
Authetec Benchmark Evaluation Framework
========================================

Generates machine-readable (JSON) and human-readable (Markdown)
reports for every benchmark run.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from benchmarks.adapters.base import BenchmarkResult


REPORTS_DIR = Path(__file__).resolve().parents[1] / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def save_results(result: BenchmarkResult) -> str:
    """Write JSON + Markdown reports and return the JSON path."""
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = result.model_name.replace(" ", "_").replace("/", "_")
    json_path = REPORTS_DIR / f"{safe_name}_{run_id}.json"
    md_path = REPORTS_DIR / f"{safe_name}_{run_id}.md"

    # ── JSON report ──
    json_data = {
        "model": result.model_name,
        "version": result.model_version,
        "dataset": result.dataset_name,
        "dataset_version": result.dataset_version,
        "features": result.features,
        "splits": {
            "train": result.train_split,
            "validation": result.validation_split,
            "test": result.test_split,
        },
        "metrics": result.metrics,
        "threshold": result.threshold,
        "latency_ms": result.latency_ms,
        "leakage_notes": result.leakage_notes,
        "reproducibility": result.reproducibility_info,
        "limitations": result.limitations,
        "generated_at": datetime.now().isoformat(),
        "model_id": result.model_id,
    }
    json_path.write_text(json.dumps(json_data, indent=2, default=str))

    # ── Markdown report ──
    md_lines: List[str] = [
        f"# Benchmark Report — {result.model_name}",
        "",
        f"**Generated:** {datetime.now().isoformat()}",
        f"**Model ID:** {result.model_id}",
        "",
        "## Dataset",
        f"- Name: {result.dataset_name}",
        f"- Version: {result.dataset_version}",
        f"- Source: {result.dataset_url}",
        "",
        "## Data Splits",
        f"- Train: {result.train_split}",
        f"- Validation: {result.validation_split}",
        f"- Test: {result.test_split}",
        "",
        "## Features",
        ", ".join(result.features) if result.features else "(see reproducibility notes)",
        "",
        "## Metrics",
        "",
        "| Metric | Value |",
        "|--------|-------|",
    ]
    for k, v in sorted(result.metrics.items()):
        md_lines.append(f"| {k} | {v:.6f} |")
    md_lines += [
        "",
        f"**Decision Threshold:** {result.threshold}",
        f"**Latency:** {result.latency_ms:.2f} ms",
        "",
        "## Leakage Analysis",
        result.leakage_notes,
        "",
        "## Reproducibility",
        json.dumps(result.reproducibility_info, indent=2),
        "",
        "## Limitations",
    ]
    for lim in result.limitations:
        md_lines.append(f"- {lim}")
    md_lines.append("")

    md_path.write_text("\n".join(md_lines))

    return str(json_path)
