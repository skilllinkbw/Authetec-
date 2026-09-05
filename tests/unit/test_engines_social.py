"""Unit tests for the Social Trust Engine.

Covers: benign-vs-suspicious separation, non-discrimination guarantees,
explainability, determinism, and failure-safe behaviour on unusual input.
"""

from __future__ import annotations

import pytest

from app.engines.social import (
    EXCLUDED_ATTRIBUTES,
    SocialProfileInput,
    SocialTrustEngine,
)
from app.models.risk import Decision


@pytest.fixture()
def engine() -> SocialTrustEngine:
    return SocialTrustEngine()


def _benign() -> SocialProfileInput:
    return SocialProfileInput(
        profile_id="p-benign",
        account_age_days=1200,
        email_verified=True,
        phone_verified=True,
        email_domain="example.com",
        profile_image_present=True,
        bio_present=True,
        post_count=60,
        following_count=40,
        follower_count=25,
        post_frequency_per_day=1.0,
        links=[],
        suspension_history_count=0,
    )


def test_benign_profile_clears(engine):
    result = engine.score(_benign())
    assert result.decision == Decision.CLEAR
    assert result.risk_score < 0.30
    assert result.engine == "social"


def test_brand_new_account_raises_risk(engine):
    profile = _benign()
    profile.account_age_days = 0.2
    fresh = engine.score(profile)
    profile.account_age_days = 400
    established = engine.score(profile)
    assert fresh.risk_score > established.risk_score
    assert fresh.decision != Decision.CLEAR


def test_machine_generated_username_flagged(engine):
    profile = _benign()
    profile.username = "x7f9k2q4m8z1a5c3"
    result = engine.score(profile)
    names = [s.name for s in result.signals]
    assert "username_pattern" in names
    sig = next(s for s in result.signals if s.name == "username_pattern")
    assert sig.value > 0


def test_disposable_email_and_unverified_signals(engine):
    profile = _benign()
    profile.email_verified = False
    profile.email_domain = "mailinator.com"
    result = engine.score(profile)
    names = [s.name for s in result.signals]
    assert "email_verification" in names
    assert "email_disposable_domain" in names


def test_identity_consistency_mismatch_adds_risk(engine):
    consistent = _benign()
    consistent.declared_country = "bw"
    consistent.phone_calling_code = "267"
    consistent.name_matches_document = True
    r_ok = engine.score(consistent)

    mismatched = SocialProfileInput(
        profile_id="p-mismatch",
        account_age_days=800,
        declared_country="bw",
        phone_calling_code="91",          # India code vs Botswana
        name_matches_document=False,
    )
    r_bad = engine.score(mismatched)
    assert r_bad.risk_score > r_ok.risk_score
    names = [s.name for s in r_bad.signals]
    assert "country_phone_mismatch" in names
    assert "name_document_mismatch" in names


def test_external_signals_are_labelled_external(engine):
    profile = _benign()
    profile.network_risk = 0.9
    profile.ip_reputation = 0.1
    result = engine.score(profile)
    external = result.extra["external_signals"]
    assert set(external) == {"network_risk", "ip_reputation"}
    sources = {s.source for s in result.signals}
    assert "external_graph" in sources


def test_protected_attributes_are_never_used(engine):
    # The engine API has no fields for protected attributes; the excluded
    # list is explicit and surfaced in every result.
    result = engine.score(_benign())
    recorded = set(result.extra["excluded_attributes"])
    assert recorded == set(EXCLUDED_ATTRIBUTES)
    assert "ethnicity" in recorded
    # And no signal name collides with a protected attribute.
    assert all("gender" not in s.name and "race" not in s.name
               for s in result.signals)


def test_decision_is_deterministic(engine):
    r1 = engine.score(_benign())
    r2 = engine.score(_benign())
    assert r1.risk_score == r2.risk_score
    assert r1.decision == r2.decision


def test_low_activity_profile_never_blocks_on_completeness_alone(engine):
    # A sparse but otherwise healthy profile must not be BLOCKED by the
    # completeness signal alone — no decision on a single signal.
    profile = SocialProfileInput(profile_id="sparse", account_age_days=90)
    result = engine.score(profile)
    assert result.decision in (Decision.CLEAR, Decision.REVIEW)


def test_every_result_is_explainable(engine):
    profile = _benign()
    profile.suspension_history_count = 2
    profile.post_frequency_per_day = 80
    result = engine.score(profile)
    assert result.reasons
    assert any("suspension" in r for r in result.reasons)
    assert any("velocity" in r or "frequency" in r for r in result.reasons)