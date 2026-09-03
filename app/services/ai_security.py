"""
AI Security Monitor
===================

Deterministic guard-rails around AI/LLM usage in Authetec.  The
platform never lets a model make an irreversible decision on its own;
every model-assisted decision passes through these policy controls.

Capabilities:
  * Prompt-injection screening   — detect instruction-override and
    jailbreak patterns in incoming prompts (deterministic heuristics;
    NOT a replacement for a dedicated adversarial-input model).
  * Secret-leak detection        — detect API keys, tokens, private keys
    and credential-shaped values in prompts and model outputs (data
    loss prevention before content is logged or sent downstream).
  * Input/output validation      — size limits and structural checks
    with explicit pass/fail notes.
  * Model integrity checks       — registered models must be APPROVED or
    PRODUCTION in the model registry before they may serve decisions.
  * Structured telemetry         — every screening produces a structured
    event (screening id, scores, signals, verdict, model version,
    timestamp) that can be persisted to the ``ai_security_events``
    table (see ``db/schema.sql``) and mirrored to the audit log.

All detection is rules-based and explainable; no score here is a
claim of measured adversarial-detection accuracy.
"""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.models.risk import Decision

logger = logging.getLogger("authetec.ai_security")

MODEL_VERSION = "ai-security-heuristics-v1"

MAX_PROMPT_CHARS = 100_000
MAX_CONTEXT_CHARS = 2_000

# ── Prompt-injection heuristics ───────────────────────────────────────────
# Name -> (compiled regex, weight).  Patterns are lower-confidence content
# signals; decisions are made only at the policy layer on the aggregate.
PROMPT_INJECTION_PATTERNS: List[tuple] = [
    ("ignore_previous", re.compile(
        r"\b(?:ignore|disregard|forget|skip|override)\s+(?:all\s+)?"
        r"(?:previous|prior|above|earlier)\s+(?:instructions|prompts|content|messages)\b",
        re.IGNORECASE), 0.60),
    ("system_breakout", re.compile(
        r"(?:reveal|print|output|show)\s+(?:your\s+)?(?:system\s+)?"
        r"(?:prompt|instructions|system message)\b", re.IGNORECASE), 0.55),
    ("role_impersonation", re.compile(
        r"\b(?:act|pretend|behave|roleplay|respond)\s+as\b", re.IGNORECASE), 0.30),
    ("privilege_escalation", re.compile(
        r"\b(?:developer\s+mode|jailbreak|dan\s*mode|super\s*user\s+mode|"
        r"god\s+mode|admin\s+override|access\s+granted)\b", re.IGNORECASE), 0.70),
    ("directive_boundary", re.compile(
        r"```\s*(?:system|developer|instruction)|\]\s*\{\s*role\s*[:=]|<\s*system\s*>",
        re.IGNORECASE), 0.65),
    ("encoded_instruction", re.compile(
        r"(?:base64|rot13|reverse the text|decode the following|caesar)",
        re.IGNORECASE), 0.40),
    ("repetition_attack", re.compile(
        r"\b(?:repeat|say|reply|output)\b.{0,40}\b(?:after|following|this)\b",
        re.IGNORECASE), 0.35),
]

# ── Credential / secret patterns (data-loss prevention) ───────────────────
SECRET_PATTERNS: List[tuple] = [
    ("openai_key", re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b")),
    ("anthropic_key", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{16,}\b")),
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
    ("slack_token", re.compile(r"\bxox[a-z]-[A-Za-z0-9-]{10,}\b")),
    ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("google_api_key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("stripe_key", re.compile(r"\bsk_live_[0-9A-Za-z]{20,}\b")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")),
    ("private_key_block", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("credential_assignment", re.compile(
        r"\b(?:api[_-]?key|secret|token|password)\s*[:=]\s*[\"']?[A-Za-z0-9_\-./+]{8,}",
        re.IGNORECASE)),
]


@dataclass
class ScreeningSignal:
    """One named detection from a screening pass."""
    name: str
    detail: str = ""
    severity: float = 0.0


@dataclass
class AiScreenResult:
    """Structured, auditable record of one AI screening."""
    screening_id: str
    mode: str                      # "prompt" | "output"
    decision: Decision
    prompt_injection_score: float = 0.0
    secret_leak_score: float = 0.0
    validation_valid: bool = True
    validation_notes: List[str] = field(default_factory=list)
    signals: List[ScreeningSignal] = field(default_factory=list)
    reasons: List[str] = field(default_factory=list)
    model_version: str = MODEL_VERSION
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "screening_id": self.screening_id,
            "mode": self.mode,
            "decision": self.decision.value,
            "prompt_injection_score": self.prompt_injection_score,
            "secret_leak_score": self.secret_leak_score,
            "validation_valid": self.validation_valid,
            "validation_notes": self.validation_notes,
            "signals": [s.__dict__ for s in self.signals],
            "reasons": self.reasons,
            "model_version": self.model_version,
            "timestamp": self.timestamp,
        }


class AiSecurityMonitor:
    """Rule-based screening pass over prompts and model outputs."""

    MODEL_VERSION = MODEL_VERSION

    # ── main entry points ─────────────────────────────────────────────

    def screen_prompt(self, text: str, context: str = "") -> AiScreenResult:
        """Screen an inbound prompt before it reaches any model."""
        return self._screen(text, context=context, mode="prompt", allow_injection=True)

    def screen_output(self, text: str) -> AiScreenResult:
        """Screen a model output for secret leakage before storage."""
        return self._screen(text, context="", mode="output", allow_injection=False)

    def _screen(self, text: str, *, context: str,
                mode: str, allow_injection: bool) -> AiScreenResult:
        result = AiScreenResult(
            screening_id=uuid.uuid4().hex,
            mode=mode,
            decision=Decision.CLEAR,
        )
        if not text or not text.strip():
            result.validation_valid = False
            result.validation_notes.append("Empty input")
            result.reasons.append("Empty input rejected")
            result.decision = Decision.REVIEW
            return result
        if len(text) > MAX_PROMPT_CHARS:
            result.validation_valid = False
            result.validation_notes.append(
                f"Input exceeds the {MAX_PROMPT_CHARS} character limit")
            result.reasons.append("Oversized input rejected")
            result.decision = Decision.BLOCK
        if context and len(context) > MAX_CONTEXT_CHARS:
            result.validation_notes.append(
                f"Context exceeds {MAX_CONTEXT_CHARS} characters; "
                "scanned truncated view only")

        # Prompt-injection pass (prompts only)
        if allow_injection:
            injection_peaks: List[float] = []
            for name, pattern, weight in PROMPT_INJECTION_PATTERNS:
                if pattern.search(text):
                    result.signals.append(ScreeningSignal(
                        name=f"injection:{name}", detail=pattern.pattern,
                        severity=weight))
                    injection_peaks.append(weight)
            if injection_peaks:
                result.prompt_injection_score = min(
                    1.0, max(injection_peaks) + 0.1 * (len(injection_peaks) - 1))

        # Secret-leak pass (both modes)
        for name, pattern in SECRET_PATTERNS:
            m = pattern.search(text)
            if m:
                matched = m.group(0)
                # Never echo the full match; a masked prefix is enough.
                masked = matched[:4] + "…" if len(matched) > 8 else "…"
                result.signals.append(ScreeningSignal(
                    name=f"secret:{name}",
                    detail=f"credential-shaped value {masked}",
                    severity=0.90))
                result.secret_leak_score = max(result.secret_leak_score, 0.90)

        # Policy mapping
        if result.secret_leak_score >= 0.90:
            result.reasons.append(
                "Secret/credential-shaped content detected — block and redact")
            result.decision = Decision.BLOCK
        elif result.prompt_injection_score >= 0.70:
            result.reasons.append(
                "Strong prompt-injection indicators — human review required")
            result.decision = Decision.BLOCK
        elif result.prompt_injection_score >= 0.35:
            result.reasons.append(
                "Possible prompt-injection indicators — human review recommended")
            result.decision = Decision.REVIEW
        elif not result.validation_valid:
            result.reasons.append("Validation failed but no adversarial/secret signals")
        else:
            result.reasons.append("No adversarial or credential signals detected")

        logger.info("ai screen id=%s mode=%s decision=%s inj=%.2f secret=%.2f",
                    result.screening_id, mode, result.decision.value,
                    result.prompt_injection_score, result.secret_leak_score)
        return result

    # ── model integrity ────────────────────────────────────────────────

    def verify_model_integrity(self, model_id: str) -> Dict[str, Any]:
        """Return whether a registered model may serve decisions.

        Only APPROVED / PRODUCTION models pass; everything else is
        rejected with the reason surfaced for audit.
        """
        try:
            from app.services.model_registry import ModelStatus, get_model_registry
            model = get_model_registry().get(model_id)
        except Exception as e:  # registry must never block silently
            logger.error("model integrity check unavailable: %s", e)
            return {"model_id": model_id, "allowed": False,
                    "reason": "model_registry_unavailable"}
        if model is None:
            return {"model_id": model_id, "allowed": False,
                    "reason": "model_not_registered"}
        allowed = model.status in (ModelStatus.APPROVED, ModelStatus.PRODUCTION)
        return {
            "model_id": model_id,
            "name": model.name,
            "version": model.version,
            "status": model.status.value,
            "allowed": allowed,
            "reason": ("approved_for_serving" if allowed
                       else "model_not_approved_for_serving"),
        }

    # ── telemetry ──────────────────────────────────────────────────────

    def record_telemetry(self, *, tenant_id: str,
                         result: AiScreenResult,
                         correlation_id: str = "") -> None:
        """Persist a structured event and mirror it to the audit log.

        Never blocks the request path; failures degrade to a log line.
        The raw screened text is never persisted.
        """
        try:
            from app.services.audit import get_audit_logger
            get_audit_logger().log(
                event_type="ai.screen",
                tenant_id=tenant_id,
                resource_type="ai_screening",
                resource_id=result.screening_id,
                action="screen",
                result=result.decision.value.lower(),
                correlation_id=correlation_id or None,
                metadata={
                    "mode": result.mode,
                    "prompt_injection_score": result.prompt_injection_score,
                    "secret_leak_score": result.secret_leak_score,
                    "validation_valid": result.validation_valid,
                    "model_version": result.model_version,
                },
            )
        except Exception as e:
            logger.debug("ai telemetry audit skipped: %s", e)
        # Optional database persistence (ai_security_events table).
        try:
            from app.infrastructure.supabase import get_supabase
            sb = get_supabase()
            if sb.available:
                sb.insert("ai_security_events", [{
                    "screening_id": result.screening_id,
                    "tenant_id": tenant_id,
                    "mode": result.mode,
                    "decision": result.decision.value,
                    "prompt_injection_score": result.prompt_injection_score,
                    "secret_leak_score": result.secret_leak_score,
                    "validation_valid": result.validation_valid,
                    "correlation_id": correlation_id or "",
                    "model_version": result.model_version,
                    "signals": [s.__dict__ for s in result.signals],
                }])
        except Exception as e:
            logger.debug("ai telemetry persistence skipped: %s", e)

    # ── health ─────────────────────────────────────────────────────────

    def health(self) -> Dict[str, Any]:
        from app.services.model_registry import get_model_registry
        reg = get_model_registry()
        return {
            "detectors": {
                "prompt_injection": len(PROMPT_INJECTION_PATTERNS),
                "secret_leak": len(SECRET_PATTERNS),
            },
            "model_registry": reg.health(),
            "model_version": self.MODEL_VERSION,
        }


_monitor: Optional[AiSecurityMonitor] = None


def get_ai_security_monitor() -> AiSecurityMonitor:
    global _monitor
    if _monitor is None:
        _monitor = AiSecurityMonitor()
    return _monitor