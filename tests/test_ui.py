from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest
from starlette.testclient import TestClient

from models import Claim, ClaimSummary, FreshnessReport, ScoredClaim
from ui.app import _annotate_answer, app


# --- Helpers ---

def make_scored(
    claim_text: str = "GPT-4 costs $0.03/1K tokens",
    category: str = "price",
    subject: str = "GPT-4",
    status: str = "contradicted",
    reasoning: str = "Price changed.",
    evidence: str | None = "Now $0.01/1K",
    source_url: str | None = "https://openai.com/pricing",
    source_date: str | None = "2026-03-01",
) -> ScoredClaim:
    return ScoredClaim(
        claim=Claim(
            claim=claim_text,
            category=category,
            verbatim_quote=claim_text,
            subject=subject,
        ),
        status=status,
        reasoning=reasoning,
        contradicting_evidence=evidence,
        source_url=source_url,
        source_date=source_date,
    )


def make_report(claims: list[ScoredClaim], mode: str = "demo") -> FreshnessReport:
    return FreshnessReport(
        original_answer=" ".join(c.claim.verbatim_quote for c in claims),
        claims=claims,
        summary=ClaimSummary(
            total=len(claims),
            confirmed=sum(1 for c in claims if c.status == "confirmed_current"),
            contradicted=sum(1 for c in claims if c.status == "contradicted"),
            unverifiable=sum(1 for c in claims if c.status == "unverifiable"),
        ),
        mode=mode,
        duration_ms=42,
    )


@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def client_exc():
    """Client that surfaces server exceptions for debugging."""
    return TestClient(app, raise_server_exceptions=True)


# --- Unit: _annotate_answer ---

def test_annotate_contradicted_claim():
    scored = make_scored(status="contradicted")
    out = _annotate_answer(scored.claim.verbatim_quote, [scored])
    assert "fc-contradicted" in out
    assert "✗ Contradicted" in out


def test_annotate_confirmed_claim():
    scored = make_scored(status="confirmed_current", evidence=None, source_url=None)
    out = _annotate_answer(scored.claim.verbatim_quote, [scored])
    assert "fc-confirmed" in out
    assert "✓ Confirmed" in out


def test_annotate_unverifiable_claim():
    scored = make_scored(status="unverifiable", evidence=None, source_url=None)
    out = _annotate_answer(scored.claim.verbatim_quote, [scored])
    assert "fc-unverifiable" in out
    assert "? Unverifiable" in out


def test_annotate_includes_source_link_for_contradicted():
    scored = make_scored(status="contradicted", source_url="https://openai.com/pricing")
    out = _annotate_answer(scored.claim.verbatim_quote, [scored])
    assert "https://openai.com/pricing" in out
    assert "fc-source-link" in out


def test_annotate_no_source_link_for_confirmed():
    scored = make_scored(status="confirmed_current", evidence=None, source_url="https://openai.com/pricing")
    out = _annotate_answer(scored.claim.verbatim_quote, [scored])
    assert "fc-source-link" not in out


def test_annotate_empty_claims():
    out = _annotate_answer("some plain answer", [])
    assert "fc-" not in out
    assert "some plain answer" in out


def test_annotate_quote_not_in_answer():
    scored = make_scored(claim_text="completely different text")
    out = _annotate_answer("original answer text", [scored])
    assert "fc-" not in out


def test_annotate_html_escapes_original():
    out = _annotate_answer("<script>alert(1)</script>", [])
    assert "<script>" not in out
    assert "&lt;script&gt;" in out


def test_annotate_newlines_become_br():
    out = _annotate_answer("line one\nline two", [])
    assert "<br>" in out


def test_annotate_longest_quote_first():
    """Longer verbatim_quote wrapped first avoids nested/double replacement."""
    short = make_scored(claim_text="GPT-4", status="confirmed_current", evidence=None, source_url=None)
    long_ = make_scored(claim_text="GPT-4 costs $0.03/1K tokens", status="contradicted")
    answer = "GPT-4 costs $0.03/1K tokens per request."
    out = _annotate_answer(answer, [short, long_])
    # Should have exactly one mark for the long quote
    assert out.count("<mark") == 1
    assert "fc-contradicted" in out


# --- GET / ---

def test_index_returns_200(client):
    r = client.get("/")
    assert r.status_code == 200


def test_index_contains_freshcheck(client):
    r = client.get("/")
    assert "FreshCheck" in r.text


def test_index_shows_demo_badge(client):
    r = client.get("/")
    assert "DEMO" in r.text


def test_index_demo_mode_shows_fixture_selector(client):
    r = client.get("/")
    assert "fixture-select" in r.text
    assert "LLM Pricing" in r.text or "Outdated" in r.text or "demo" in r.text.lower()


def test_index_production_mode_no_fixture_selector(client, monkeypatch):
    import config
    monkeypatch.setattr(config.settings, "app_mode", config.AppMode.PRODUCTION)
    r = client.get("/")
    assert "fixture-select" not in r.text


# --- GET /health ---

def test_health_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert data["mode"] in ("demo", "production")


# --- POST /check ---

def test_check_empty_body_returns_422(client):
    r = client.post("/check", json={"llm_answer": ""})
    assert r.status_code == 422
    assert "error" in r.json()


def test_check_whitespace_only_returns_422(client):
    r = client.post("/check", json={"llm_answer": "   "})
    assert r.status_code == 422


def test_check_missing_field_returns_422(client):
    r = client.post("/check", json={})
    assert r.status_code == 422


def test_check_success_shape(client):
    report = make_report([make_scored()])
    with patch("ui.app.run_pipeline", new=AsyncMock(return_value=report)):
        r = client.post("/check", json={"llm_answer": "GPT-4 costs $0.03/1K tokens."})
    assert r.status_code == 200
    data = r.json()
    assert "annotated_answer" in data
    assert "summary" in data
    assert "claims" in data
    assert "mode" in data
    assert "duration_ms" in data


def test_check_summary_fields_present(client):
    report = make_report([make_scored()])
    with patch("ui.app.run_pipeline", new=AsyncMock(return_value=report)):
        r = client.post("/check", json={"llm_answer": "GPT-4 costs $0.03/1K tokens."})
    s = r.json()["summary"]
    assert all(k in s for k in ("total", "confirmed", "contradicted", "unverifiable"))


def test_check_claims_fields_present(client):
    report = make_report([make_scored()])
    with patch("ui.app.run_pipeline", new=AsyncMock(return_value=report)):
        r = client.post("/check", json={"llm_answer": "GPT-4 costs $0.03/1K tokens."})
    claim = r.json()["claims"][0]
    assert all(k in claim for k in ("claim", "category", "status", "reasoning", "source_url", "source_date"))


def test_check_annotated_answer_contains_mark(client):
    report = make_report([make_scored()])
    with patch("ui.app.run_pipeline", new=AsyncMock(return_value=report)):
        r = client.post("/check", json={"llm_answer": "GPT-4 costs $0.03/1K tokens."})
    assert "<mark" in r.json()["annotated_answer"]


def test_check_no_claims_returns_empty_list(client):
    report = make_report([])
    with patch("ui.app.run_pipeline", new=AsyncMock(return_value=report)):
        r = client.post("/check", json={"llm_answer": "AI is generally helpful."})
    assert r.status_code == 200
    assert r.json()["claims"] == []
    assert r.json()["summary"]["total"] == 0


def test_check_pipeline_error_returns_500(client):
    from exceptions import PipelineError
    with patch("ui.app.run_pipeline", new=AsyncMock(side_effect=PipelineError("Bifrost down"))):
        r = client.post("/check", json={"llm_answer": "some answer"})
    assert r.status_code == 500
    assert "Bifrost down" in r.json()["error"]


def test_check_demo_mode_response(client):
    r = client.post("/check", json={"llm_answer": "GPT-4 Turbo costs $0.01 per 1K input tokens and $0.03 per 1K output tokens."})
    assert r.status_code == 200
    data = r.json()
    assert data["mode"] == "demo"
    assert data["summary"]["total"] >= 0
