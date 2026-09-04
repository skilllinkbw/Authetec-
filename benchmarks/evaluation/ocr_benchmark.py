"""
OCR / MRZ Benchmark Framework (SYNTHETIC / TEST-ONLY)
=====================================================

Repeatable benchmark that reports, where data exists:

  * character accuracy
  * field accuracy
  * MRZ validity rate
  * false acceptance rate (tampered MRZ accepted)
  * false rejection rate (valid MRZ rejected)
  * processing failures

IMPORTANT HONESTY CONSTRAINT
----------------------------
This benchmark runs on SYNTHETICALLY generated and SYNTHETICALLY
degraded MRZ strings (programmatic character noise).  It does NOT use
real-world document scans.  Every number it produces is a property of
the synthetic noise model — it is NOT a real-world OCR accuracy figure
and must never be presented as one.  Real-dataset validation remains a
documented production blocker (see AUTHEC_PRODUCTION_HARDENING_REPORT).

Usage:
    python -m benchmarks.evaluation.ocr_benchmark --samples 500
"""

from __future__ import annotations

import argparse
import json
import os
import random
import string
from dataclasses import dataclass, field, asdict
from typing import Dict, List

from app.engines.mrz import compute_check_digit, validate_mrz

# Explicit provenance labels embedded in every report.
DATASET_LABEL = "SYNTHETIC/TEST-ONLY"
NOISE_ALPHABET = string.ascii_uppercase + string.digits + "<"


@dataclass
class OcrBenchmarkReport:
    """Result container — every field is synthetic-only provenance."""

    dataset: str = DATASET_LABEL
    n_samples: int = 0
    noise_rate: float = 0.0
    character_accuracy: float = 0.0     # synthetic OCR chars correct
    field_accuracy: float = 0.0         # document_number + dob + expiry exact
    mrz_validity_rate: float = 0.0      # fraction of (degraded) MRZs valid
    false_acceptance_rate: float = 0.0  # tampered MRZs accepted (synthetic)
    false_rejection_rate: float = 0.0   # valid MRZs rejected (synthetic)
    processing_failures: int = 0        # exceptions during evaluation
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        d = asdict(self)
        d["disclaimer"] = (
            "All metrics are computed on SYNTHETICALLY generated and "
            "degraded MRZ data. They are NOT real-world accuracy figures."
        )
        return d


def _build_td3(rng: random.Random) -> List[str]:
    """Generate a random, self-consistent TD3 MRZ."""
    def rand_field(n, alphabet=string.ascii_uppercase + string.digits):
        return "".join(rng.choice(alphabet) for _ in range(n))

    docnum = rand_field(9)
    nat = "UTO"
    dob = f"{rng.randint(30, 99):02d}{rng.randint(1, 12):02d}{rng.randint(1, 28):02d}"
    sex = rng.choice("MF")
    exp = f"{rng.randint(0, 40):02d}{rng.randint(1, 12):02d}{rng.randint(1, 28):02d}"
    name = "ERIKSSON<<ANNA<MARIA"
    dnc, dbc, ec = (str(compute_check_digit(x)) for x in (docnum, dob, exp))
    opt = "<" * 14  # TD3 optional data field is 14 chars
    oc = str(compute_check_digit(opt))
    final = str(compute_check_digit(docnum + dnc + dob + dbc + exp + ec + opt + oc))
    l1 = ("P<UTO" + name).ljust(44, "<")
    l2 = docnum + dnc + nat + dob + dbc + sex + exp + ec + opt + oc + final
    return [l1, l2]


def _degrade_line(line: str, rate: float, rng: random.Random) -> str:
    """Simulate OCR noise: substitution / insertion / deletion per char."""
    out: List[str] = []
    for ch in line:
        r = rng.random()
        if r < rate * 0.6:
            out.append(rng.choice(NOISE_ALPHABET))   # substitution
        elif r < rate * 0.8:
            continue                                  # deletion
        elif r < rate:
            out.append(ch)
            out.append(rng.choice(NOISE_ALPHABET))   # insertion
        else:
            out.append(ch)
    return "".join(out)


def run_ocr_benchmark(n_samples: int = 300, noise_rate: float = 0.02,
                      seed: int = 42) -> OcrBenchmarkReport:
    """Run the synthetic benchmark. Deterministic for a given seed."""
    rng = random.Random(seed)
    report = OcrBenchmarkReport(n_samples=n_samples, noise_rate=noise_rate)
    char_ok = char_total = field_ok = 0
    valid_count = 0
    tamper_accept = tamper_total = 0
    clean_reject = 0

    for _ in range(n_samples):
        try:
            lines = _build_td3(rng)

            # -- clean baseline: must validate -------------------------
            base = validate_mrz(list(lines))
            if not base.is_valid:
                clean_reject += 1

            # -- synthetic OCR degradation ------------------------------
            degraded = [_degrade_line(l, noise_rate, rng) for l in lines]
            for a, b in zip(lines, degraded):
                char_total += len(a)
                char_ok += sum(1 for x, y in zip(a, b) if x == y)
            r = validate_mrz(degraded)
            if r.is_valid:
                valid_count += 1
            fields = r.fields
            expected = base.fields
            if (fields.get("document_number") == expected.get("document_number")
                    and fields.get("date_of_birth") == expected.get("date_of_birth")
                    and fields.get("expiry_date") == expected.get("expiry_date")):
                field_ok += 1

            # -- synthetic tampering: must be rejected ------------------
            t = list(lines)
            idx = rng.randrange(0, 9)
            repl = rng.choice(NOISE_ALPHABET)
            while repl == t[1][idx]:
                repl = rng.choice(NOISE_ALPHABET)
            t[1] = t[1][:idx] + repl + t[1][idx + 1:]
            tamper_total += 1
            if validate_mrz(t).is_valid:
                tamper_accept += 1
        except Exception:
            report.processing_failures += 1

    n = max(n_samples, 1)
    report.character_accuracy = round(char_ok / max(char_total, 1), 4)
    report.field_accuracy = round(field_ok / n, 4)
    report.mrz_validity_rate = round(valid_count / n, 4)
    report.false_acceptance_rate = round(tamper_accept / max(tamper_total, 1), 4)
    report.false_rejection_rate = round(clean_reject / n, 4)
    report.notes.append(
        "Mod-10 check digits inherently miss alterations that shift the "
        "weighted sum by a multiple of 10; residual FAR is expected.")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="SYNTHETIC OCR/MRZ benchmark")
    parser.add_argument("--samples", type=int, default=300)
    parser.add_argument("--noise", type=float, default=0.02)
    parser.add_argument("--out", default="benchmarks/reports/ocr_benchmark.json")
    args = parser.parse_args()

    report = run_ocr_benchmark(n_samples=args.samples, noise_rate=args.noise)
    payload = report.to_dict()
    print(json.dumps(payload, indent=2))
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(payload, f, indent=2)
    print(f"\nReport written to {args.out} ({DATASET_LABEL})")


if __name__ == "__main__":
    main()
