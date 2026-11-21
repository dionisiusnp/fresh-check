from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from freshness_scorer import _all_results_too_old, _format_results, _is_too_old, _parse_verdict, score_claim
from models import Claim, SearchResult, VerifiedClaim


# --- Helpers ---

def make_claim(
    claim: str = "GPT-4 costs $0.03/1K tokens",
    category: str = "price",
    subject: str = "GPT-4",
) -> Claim:
    return Claim(claim=claim, category=category, verbatim_quote=claim, subject=subject)


def make_result(
    title: str = "OpenAI Pricing",
    url: str = "https://openai.com/pricing",
    snippet: str = "GPT-4 Turbo costs $0.01 per 1K input tokens.",
    published_date: str | None = "2026-06-01",
    score: float = 0.9,
) -> SearchResult:
    return SearchResult(title=title, url=url, snippet=snippet, published_date=published_date, score=score)


def make_verified(
    claim: Claim | None = None,
    results: list[SearchResult] | None = None,
    search_error: str | None = None,
) -> VerifiedClaim:
    return VerifiedClaim(
        claim=claim or make_claim(),
        query_used="test query",
        results=results if results is not None else [make_result()],
        search_error=search_error,
    )


def mock_llm_response(status: str, reasoning: str = "test", evidence: str | None = None, url: str | None = None) -> MagicMock:
    payload = {"status": status, "reasoning": reasoning, "contradicting_evidence": evidence, "source_url": url}
    msg = MagicMock()
    msg.content = json.dumps(payload)
    choice = MagicMock()
    choice.message = msg
    response = MagicMock()
    response.choices = [choice]
    return response


@pytest.fixture
def mock_bifrost():
    with patch("freshness_scorer._make_client") as mock_make:
        client = AsyncMock()
        client.chat.completions.create = AsyncMock()
        mock_make.return_value = client
        yield client


# --- Unit: _is_too_old ---

def _date_years_ago(years: float) -> str:
    d = datetime.now(timezone.utc) - timedelta(days=int(years * 365.25))
    return d.strftime("%Y-%m-%d")


def test_is_too_old_recent_date():
    assert _is_too_old(_date_years_ago(0.5)) is False


def test_is_too_old_exactly_at_threshold():
    assert _is_too_old(_date_years_ago(2.1)) is True


def test_is_too_old_ancient():
    assert _is_too_old("2019-01-01") is True


def test_is_too_old_none():
    assert _is_too_old(None) is False


def test_is_too_old_malformed_date():
    assert _is_too_old("not-a-date") is False


# --- Unit: _all_results_too_old ---

def test_all_results_too_old_all_old():
    results = [make_result(published_date="2019-01-01"), make_result(published_date="2020-06-01")]
    assert _all_results_too_old(results) is True


def test_all_results_too_old_one_recent():
    results = [make_result(published_date="2019-01-01"), make_result(published_date=_date_years_ago(0.5))]
    assert _all_results_too_old(results) is False


def test_all_results_too_old_no_dates():
    results = [make_result(published_date=None)]
    assert _all_results_too_old(results) is False


def test_all_results_too_old_empty():
    assert _all_results_too_old([]) is False


# --- Unit: _parse_verdict ---

def test_parse_verdict_valid():
    raw = json.dumps({"status": "confirmed_current", "reasoning": "ok", "contradicting_evidence": None, "source_url": None})
    data = _parse_verdict(raw)
    assert data["status"] == "confirmed_current"


def test_parse_verdict_strips_markdown():
    raw = "```json\n" + json.dumps({"status": "contradicted", "reasoning": "r", "contradicting_evidence": "e", "source_url": "http://x.com"}) + "\n```"
    data = _parse_verdict(raw)
    assert data["status"] == "contradicted"


def test_parse_verdict_invalid_raises():
    import pytest
    with pytest.raises(Exception):
        _parse_verdict("not json")


# --- Unit: _format_results ---

def test_format_results_empty():
    assert _format_results([]) == "(no results)"


def test_format_results_includes_title_url_snippet():
    r = make_result(title="T", url="https://x.com", snippet="some text")
    text = _format_results([r])
    assert "T" in text
    assert "https://x.com" in text
    assert "some text" in text


def test_format_results_includes_date():
    r = make_result(published_date="2024-06-01")
    text = _format_results([r])
    assert "2024-06-01" in text


# --- Integration: score_claim (mocked Bifrost) ---

async def test_score_returns_confirmed(mock_bifrost):
    mock_bifrost.chat.completions.create.return_value = mock_llm_response("confirmed_current", "Source confirms the claim.")
    result = await score_claim(make_verified())
    assert result.status == "confirmed_current"
    assert result.reasoning == "Source confirms the claim."


async def test_score_returns_contradicted_with_evidence(mock_bifrost):
    mock_bifrost.chat.completions.create.return_value = mock_llm_response(
        "contradicted",
        reasoning="Price changed.",
        evidence="GPT-4 Turbo now costs $0.01/1K tokens",
        url="https://openai.com/pricing",
    )
    result = await score_claim(make_verified())
    assert result.status == "contradicted"
    assert result.contradicting_evidence == "GPT-4 Turbo now costs $0.01/1K tokens"
    assert result.source_url == "https://openai.com/pricing"


async def test_score_returns_unverifiable_no_results():
    verified = make_verified(results=[])
    result = await score_claim(verified)
    assert result.status == "unverifiable"
    assert "No search results" in result.reasoning


async def test_score_propagates_search_error():
    verified = make_verified(results=[], search_error="timeout")
    result = await score_claim(verified)
    assert result.status == "unverifiable"
    assert result.search_error == "timeout"
    assert "timeout" in result.reasoning


async def test_score_unverifiable_when_all_results_too_old():
    old_result = make_result(published_date="2019-03-01")
    verified = make_verified(results=[old_result])
    result = await score_claim(verified)
    assert result.status == "unverifiable"
    assert "older than" in result.reasoning


async def test_score_fallback_unverifiable_on_invalid_json(mock_bifrost):
    msg = MagicMock()
    msg.content = "I cannot determine this."
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    mock_bifrost.chat.completions.create.return_value = resp

    result = await score_claim(make_verified())
    assert result.status == "unverifiable"
    assert "invalid" in result.reasoning.lower()


async def test_score_fallback_unverifiable_on_llm_failure(mock_bifrost):
    mock_bifrost.chat.completions.create.side_effect = Exception("connection refused")
    result = await score_claim(make_verified())
    assert result.status == "unverifiable"
    assert "failed" in result.reasoning.lower()


async def test_score_unknown_status_coerced_to_unverifiable(mock_bifrost):
    mock_bifrost.chat.completions.create.return_value = mock_llm_response("maybe_true")
    result = await score_claim(make_verified())
    assert result.status == "unverifiable"


async def test_score_resolves_source_date_from_results(mock_bifrost):
    result_item = make_result(url="https://openai.com/pricing", published_date="2026-06-01")
    verified = make_verified(results=[result_item])
    mock_bifrost.chat.completions.create.return_value = mock_llm_response(
        "contradicted",
        url="https://openai.com/pricing",
    )
    scored = await score_claim(verified)
    assert scored.source_date == "2026-06-01"


async def test_score_no_source_date_when_url_not_in_results(mock_bifrost):
    mock_bifrost.chat.completions.create.return_value = mock_llm_response(
        "contradicted",
        url="https://some-other-site.com/page",
    )
    result = await score_claim(make_verified())
    assert result.source_date is None


async def test_score_skips_llm_call_when_no_results():
    """score_claim must NOT call Bifrost when results is empty."""
    with patch("freshness_scorer._make_client") as mock_make:
        verified = make_verified(results=[])
        await score_claim(verified)
        mock_make.assert_not_called()


async def test_score_skips_llm_call_on_search_error():
    """score_claim must NOT call Bifrost when search_error is set."""
    with patch("freshness_scorer._make_client") as mock_make:
        verified = make_verified(results=[], search_error="tavily_error:502")
        await score_claim(verified)
        mock_make.assert_not_called()
