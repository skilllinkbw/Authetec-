"""Configurable biometric regression gates.

Two distinct concepts:

ENGINEERING_REGRESSION_GATE
    A pass/fail check that the benchmark actually ran and produced sane,
    finite numbers inside an engineer-defined envelope.  These are not
    science claims — they catch broken pipelines and gross regressions.

PRODUCTION_ACCEPTANCE_REQUIREMENT
    A threshold that must be scientifically justified (dataset, protocol,
    target population) before it can be enforced.  Until a legitimate
    acceptance threshold has been established it MUST be reported as
    CONFIGURATION REQUIRED, never invented.

Gates with no configured limit are reported as ``skipped`` with status
CONFIGURATION REQUIRED.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# gate name -> (kind, comparison, description)
# comparison: "lower_is_better" limits are max_*; "higher_is_better" are min_*.
GATE_SPECS: Dict[str, Dict[str, Any]] = {
    "max_far": {"kind": "ENGINEERING_REGRESSION_GATE",
                "direction": "lower", "desc": "false acceptance rate"},
    "max_frr": {"kind": "ENGINEERING_REGRESSION_GATE",
                "direction": "lower", "desc": "false rejection rate"},
    "min_precision": {"kind": "ENGINEERING_REGRESSION_GATE",
                      "direction": "higher", "desc": "verification precision"},
    "min_recall": {"kind": "ENGINEERING_REGRESSION_GATE",
                   "direction": "higher", "desc": "verification recall"},
    "min_f1": {"kind": "ENGINEERING_REGRESSION_GATE",
               "direction": "higher", "desc": "verification F1"},
    "min_rocauc": {"kind": "ENGINEERING_REGRESSION_GATE",
                   "direction": "higher", "desc": "verification ROC-AUC"},
    "max_apcer": {"kind": "ENGINEERING_REGRESSION_GATE",
                  "direction": "lower", "desc": "attack classification error"},
    "max_bpcer": {"kind": "ENGINEERING_REGRESSION_GATE",
                  "direction": "lower", "desc": "bona-fide classification error"},
    "max_acer": {"kind": "ENGINEERING_REGRESSION_GATE",
                 "direction": "lower", "desc": "average classification error"},
    "max_p95_latency_ms": {"kind": "ENGINEERING_REGRESSION_GATE",
                           "direction": "lower", "desc": "p95 verification ms"},
}


@dataclass
class GateResult:
    name: str
    kind: str
    limit: Optional[float]
    value: Optional[float]
    passed: bool
    status: str   # PASS | FAIL | SKIPPED (CONFIGURATION REQUIRED)
    note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "limit": self.limit,
            "value": self.value,
            "passed": self.passed,
            "status": self.status,
            "note": self.note,
        }


class RegressionGateSet:
    """Evaluates configured gates against a flat results metric dict."""

    def __init__(self, overrides: Optional[Dict[str, float]] = None) -> None:
        self._limits: Dict[str, float] = dict(overrides or {})

    def evaluate(self, metrics: Dict[str, Any]) -> Dict[str, Any]:
        """Return {gates: [...], passed: bool, skipped: [names]}."""
        results: List[GateResult] = []
        skipped: List[str] = []
        all_passed = True
        for name in sorted(GATE_SPECS):
            spec = GATE_SPECS[name]
            limit = self._limits.get(name)
            value = metrics.get(name, metrics.get(name.replace("max_", "").replace("min_", "")))
            if limit is None:
                skipped.append(name)
                results.append(GateResult(
                    name=name, kind=spec["kind"], limit=None, value=None,
                    passed=False, status="SKIPPED",
                    note="CONFIGURATION REQUIRED - no legitimate acceptance "
                         "threshold has been established"))
                continue
            if value is None:
                results.append(GateResult(
                    name=name, kind=spec["kind"], limit=limit, value=None,
                    passed=False, status="SKIPPED",
                    note="metric not available for this run"))
                continue
            ok = (value <= limit) if spec["direction"] == "lower" \
                else (value >= limit)
            if not ok:
                all_passed = False
            results.append(GateResult(
                name=name, kind=spec["kind"], limit=limit, value=value,
                passed=ok, status="PASS" if ok else "FAIL"))
        return {
            "gates": [r.to_dict() for r in results],
            "passed": all_passed,
            "skipped": skipped,
            "configured_limits": dict(self._limits),
        }


def production_gate_example() -> Dict[str, float]:
    """ILLUSTRATIVE production-style limits.

    These are examples only.  A real production requirement must be derived
    from the deployment's threat model, target population and a lawful,
    representative dataset — never from this example dict.
    """
    return {
        "max_far": 0.001,
        "max_frr": 0.01,
        "min_f1": 0.98,
        "min_rocauc": 0.995,
        "max_apcer": 0.05,
        "max_bpcer": 0.05,
        "max_acer": 0.05,
        "max_p95_latency_ms": 1500.0,
    }