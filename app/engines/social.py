"""
Social Trust Engine
===================

Scores the trustworthiness of a social/consumer profile using an
explicit, deterministic, explainable rule set.  It is designed to be
DEFENSIBLE:

* No decision is ever based on a single superficial characteristic.
* Protected attributes (ethnicity, religion, gender identity,
  nationality, sexual orientation, disability, age) are NEVER requested
  or used as signals.  The engine documents the attributes it excludes.
* Every signal is a named, weighted, explainable rule; the final risk
  score and decision combine them transparently.
* Optional external signals (graph/network analysis, IP reputation)
  can be supplied by the caller and are clearly labelled as external.

This is a v1 rule-based engine.  It does NOT claim to detect fraud
with any measured accuracy — see ``benchmarks/social`` for the SYNTHETIC
harness that probes its decision behaviour and thresholds.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from app.core.config import get_settings
from app.models.risk import Decision, EngineResult, Signal

logger = logging.getLogger("authetec.social")

MODEL_VERSION = "social-rule-v1"

# ── Reference tables (explicit policy, not hidden model internals) ────────

# Email domains commonly used for throwaway accounts.  Only used to raise a
# signal when the caller has NOT independently verified the address.
DISPOSABLE_EMAIL_DOMAINS: frozenset = frozenset({
    "mailinator.com", "10minutemail.com", "guerrillamail.com", "temp-mail.org",
    "throwawaymail.com", "yopmail.com", "sharklasers.com", "mailnesia.com",
    "spam4.me", "trashmail.com", "fakeinbox.com", "tempmail.com",
})

# URL shorteners / redirection services common in abuse chains.
SHORTENER_DOMAINS: frozenset = frozenset({
    "bit.ly", "tinyurl.com", "goo.gl", "t.co", "buff.ly", "ow.ly",
    "is.gd", "cutt.ly", "rebrand.ly", "shorturl.at", "rb.gy", "su.pr",
})

# Rough country -> calling-code map used ONLY for the explicit identity
# consistency check (declared country vs phone country prefix).  It never
# feeds a demographic inference.
COUNTRY_CALLING_CODES: Dict[str, str] = {
    "us": "1", "ca": "1",
    "uk": "44", "gb": "44", "ie": "353",
    "za": "27", "bw": "267", "ng": "234", "ke": "254", "gh": "233",
    "in": "91", "pk": "92", "bd": "880", "lk": "94", "np": "977",
    "de": "49", "fr": "33", "es": "34", "it": "39", "nl": "31",
    "br": "55", "mx": "52", "ar": "54",
    "cn": "86", "jp": "81", "kr": "82", "sg": "65", "my": "60",
    "au": "61", "nz": "64",
}

# Usernames that look machine-generated (random alphanumeric runs) or that
# re-encode words like "admin"/"support" to impersonate trusted accounts.
_MACHINE_USERNAME_RE = re.compile(r"^(?:[a-z0-9]{16,}|[a-z][a-z0-9_]{4,}\d{6,})$")
_IMPERSONATION_RE = re.compile(
    r"(admin|support|official|service|help|bank|pay)", re.IGNORECASE)

# Attributes the engine refuses to consume — kept so policy is auditable.
EXCLUDED_ATTRIBUTES: List[str] = [
    "ethnicity", "religion", "gender_identity", "nationality_bias",
    "sexual_orientation", "disability", "age_band", "political_views",
]


@dataclass
class SocialProfileInput:
    """Profile features supplied by the caller.

    Only fields declared here are consumed.  ``network_risk`` and
    ``ip_reputation`` are OPTIONAL external signals (graph analysis,
    device/IP intelligence) and are labelled as external in the output.
    """

    profile_id: str = ""
    username: str = ""
    account_age_days: float = 365.0
    email_verified: bool = False
    phone_verified: bool = False
    email_domain: str = ""
    profile_image_present: bool = True
    bio_present: bool = True
    post_count: int = 0
    following_count: int = 0
    follower_count: int = 0
    post_frequency_per_day: float = 0.0
    links: List[str] = field(default_factory=list)
    declared_country: str = ""
    phone_calling_code: str = ""
    name_matches_document: Optional[bool] = None
    suspension_history_count: int = 0
    # ── optional external signals (documented, caller-supplied) ──────────
    network_risk: Optional[float] = None      # 0..1 from graph analysis
    ip_reputation: Optional[float] = None     # 0..1 from device/IP intel


# ── Individual deterministic signals ──────────────────────────────────────

def _account_age_signal(days: float) -> Signal:
    if days < 1:
        value, reason = 0.90, "Account created less than 1 day ago"
    elif days < 7:
        value, reason = 0.60, "Account created less than 7 days ago"
    elif days < 30:
        value, reason = 0.30, "Account created less than 30 days ago"
    else:
        value, reason = 0.0, "Account age is not a risk factor"
    return Signal("account_age", value, 0.20, reason, "social")


def _velocity_signal(freq: float) -> Signal:
    if freq >= 50:
        value = 0.85
        reason = f"Posting frequency {freq:.0f}/day is far outside human norms"
    elif freq >= 20:
        value = 0.55
        reason = f"Posting frequency {freq:.0f}/day is unusually high"
    elif freq >= 5:
        value = 0.25
        reason = f"Posting frequency {freq:.0f}/day is elevated"
    else:
        value, reason = 0.0, "Posting frequency is within normal range"
    return Signal("post_velocity", value, 0.15, reason, "social")


def _verification_signals(p: SocialProfileInput) -> List[Signal]:
    signals: List[Signal] = []
    if not p.email_verified:
        signals.append(Signal(
            "email_verification", 0.40, 0.10,
            "Email address is not verified", "social"))
    if p.email_domain.strip().lower() in DISPOSABLE_EMAIL_DOMAINS:
        signals.append(Signal(
            "email_disposable_domain", 0.60, 0.10,
            "Email domain is commonly used for throwaway accounts", "social"))
    if not p.phone_verified:
        signals.append(Signal(
            "phone_verification", 0.30, 0.10,
            "Phone number is not verified", "social"))
    return signals


def _profile_completeness_signal(p: SocialProfileInput) -> Signal:
    missing = []
    if not p.profile_image_present:
        missing.append("profile image")
    if not p.bio_present:
        missing.append("bio")
    if not p.links and p.post_count == 0:
        missing.append("activity history")
    if not missing:
        return Signal("profile_completeness", 0.0, 0.08,
                      "Profile completeness is adequate", "social")
    return Signal(
        "profile_completeness", min(0.6, 0.25 * len(missing)), 0.08,
        "Missing profile elements: " + ", ".join(missing), "social")


def _follower_ratio_signal(p: SocialProfileInput) -> Signal:
    following = max(p.following_count, 0)
    followers = max(p.follower_count, 0)
    if following >= 100 and followers <= 1:
        value = 0.70
        reason = "Follows many accounts but has no followers (possible network manipulation)"
    elif following > 0 and followers > 0 and following / followers > 50:
        value = 0.40
        reason = "Following/follower ratio is extreme"
    else:
        value, reason = 0.0, "Follow graph ratios are not anomalous"
    return Signal("follower_ratio", value, 0.08, reason, "social")


def _username_signal(username: str) -> Signal:
    uname = (username or "").strip()
    if not uname:
        return Signal("username_pattern", 0.10, 0.06,
                      "Username absent (profile not curated)", "social")
    if _MACHINE_USERNAME_RE.match(uname) or not any(ch.isalpha() for ch in uname):
        return Signal("username_pattern", 0.50, 0.06,
                      "Username appears machine-generated (random/hex pattern)", "social")
    if _IMPERSONATION_RE.search(uname):
        return Signal("username_pattern", 0.30, 0.06,
                      "Username resembles a trusted/impersonation pattern", "social")
    return Signal("username_pattern", 0.0, 0.06,
                  "Username pattern is not anomalous", "social")


def _link_risk_signal(p: SocialProfileInput) -> Signal:
    risky = [l for l in p.links if any(d in l.lower() for d in SHORTENER_DOMAINS)]
    if risky:
        return Signal("link_risk", 0.50, 0.08,
                      "Profile links use URL shorteners: " + ", ".join(risky[:3]), "social")
    return Signal("link_risk", 0.0, 0.08, "Profile links are not flagged", "social")


def _identity_consistency_signals(p: SocialProfileInput) -> List[Signal]:
    signals: List[Signal] = []
    expected = COUNTRY_CALLING_CODES.get(p.declared_country.strip().lower())
    if expected and p.phone_calling_code and p.phone_calling_code != expected:
        signals.append(Signal(
            "country_phone_mismatch", 0.40, 0.10,
            f"Declared country {p.declared_country!r} does not match the phone calling code",
            "social"))
    if p.name_matches_document is False:
        signals.append(Signal(
            "name_document_mismatch", 0.50, 0.12,
            "Profile name does not match the identity document on file", "social"))
    return signals


def _suspension_signal(count: int) -> Signal:
    if count == 0:
        return Signal("suspension_history", 0.0, 0.06,
                      "No prior platform suspensions", "social")
    value = min(0.80, 0.30 * count)
    return Signal("suspension_history", value, 0.06,
                  f"Prior platform suspensions: {count}", "social")


def _external_signals(p: SocialProfileInput) -> List[Signal]:
    signals: List[Signal] = []
    if p.network_risk is not None:
        signals.append(Signal(
            "network_risk", max(0.0, min(1.0, p.network_risk)), 0.15,
            "External graph/network risk (caller-supplied)", "external_graph"))
    if p.ip_reputation is not None:
        signals.append(Signal(
            "ip_reputation", max(0.0, min(1.0, p.ip_reputation)), 0.10,
            "External device/IP reputation (caller-supplied)", "external_device"))
    return signals


def _default_confidence(signals: List[Signal]) -> float:
    """Confidence scales with evidence strength; weak evidence => low confidence."""
    if not signals:
        return 0.35
    active = [s for s in signals if s.value > 0.0]
    if not active:
        return 0.45  # everything benign but little to go on
    total_weight = sum(s.weight for s in active)
    evidence_strength = sum(s.value * s.weight for s in active) / max(1e-9, total_weight)
    return max(0.35, min(0.90, 0.45 + evidence_strength * 0.45))


class SocialTrustEngine:
    """Evaluate a profile and return a standard EngineResult."""

    MODEL_VERSION = MODEL_VERSION

    def __init__(self) -> None:
        self._settings = get_settings()
        self._thresholds = {
            "clear": self._settings.risk_clear_threshold,
            "review": self._settings.risk_review_threshold,
        }

    def score(self, profile: SocialProfileInput,
              *, tenant_id: str = "default") -> EngineResult:
        del tenant_id  # reserved for per-tenant policy/audit wiring
        t0 = time.perf_counter()

        signals: List[Signal] = []
        signals.append(_account_age_signal(profile.account_age_days))
        signals.append(_velocity_signal(profile.post_frequency_per_day))
        signals.extend(_verification_signals(profile))
        signals.append(_profile_completeness_signal(profile))
        signals.append(_follower_ratio_signal(profile))
        signals.append(_username_signal(profile.username))
        signals.append(_link_risk_signal(profile))
        signals.extend(_identity_consistency_signals(profile))
        signals.append(_suspension_signal(profile.suspension_history_count))
        signals.extend(_external_signals(profile))

        total_weight = sum(s.weight for s in signals) or 1e-9
        weighted_risk = sum(s.value * s.weight for s in signals) / total_weight
        risk = max(0.0, min(1.0, weighted_risk))

        decision = self._decide(risk)
        reasons: List[str] = []
        # Policy floors: some conditions can never yield CLEAR even if the
        # weighted score is low, mirroring the face engine's fail-safe floors.
        floor = self._policy_floor(profile)
        if floor and decision == Decision.CLEAR:
            decision = floor["decision"]
            reasons.append(f"policy floor: {floor['reason']}")
        confidence = _default_confidence(signals)

        active = sorted((s for s in signals if s.value > 0.0),
                        key=lambda s: s.value * s.weight, reverse=True)
        if not active:
            reasons.append("No risk signals exceeded their threshold")
        else:
            for s in active[:5]:
                reasons.append(f"[{s.name}] {s.reason}")
        reasons.append("Protected attributes are never used by this engine (see EXCLUDED_ATTRIBUTES)")
        reasons.append("Rule-based v1: validate behaviour on your population before general availability")

        elapsed_ms = (time.perf_counter() - t0) * 1000
        result = EngineResult(
            engine="social",
            risk_score=round(risk, 4),
            confidence=round(confidence, 4),
            decision=decision,
            signals=signals,
            reasons=reasons,
            evidence=[],  # caller attaches evidence ids when persisting a case
            model_version=self.MODEL_VERSION,
            processing_time_ms=round(elapsed_ms, 2),
            extra={
                "profile_id": profile.profile_id,
                "signals_considered": [s.name for s in signals],
                "excluded_attributes": EXCLUDED_ATTRIBUTES,
                "external_signals": [s.name for s in signals if s.source.startswith("external")],
            },
        )
        logger.info("social risk profile=%s decision=%s risk=%.3f conf=%.3f",
                    profile.profile_id or "-", decision.value, risk, confidence)
        return result

    def _decide(self, risk: float) -> Decision:
        if risk < self._thresholds["clear"]:
            return Decision.CLEAR
        if risk < self._thresholds["review"]:
            return Decision.REVIEW
        return Decision.BLOCK

    @staticmethod
    def _policy_floor(profile: SocialProfileInput) -> Optional[dict]:
        """Return a minimum-decision policy floor, or None.

        Like the face engine, these floors guarantee that certain
        high-stakes conditions can never produce a CLEAR decision.
        """
        if profile.account_age_days < 1:
            return {"decision": Decision.REVIEW,
                    "reason": "account younger than 1 day forces at least REVIEW"}
        if profile.suspension_history_count >= 3:
            return {"decision": Decision.REVIEW,
                    "reason": "multiple prior suspensions forces at least REVIEW"}
        if profile.name_matches_document is False:
            return {"decision": Decision.REVIEW,
                    "reason": "name/document mismatch forces at least REVIEW"}
        return None