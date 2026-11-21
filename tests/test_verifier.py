from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from claim_verifier import _build_query, _parse_results, verify_claim
from models import Claim, SearchResult


# --- Helpers ---

def make_claim(
    claim: str = "GPT-4 costs $0.03/1K tokens",
    category: str = "price",
    subject: str = "GPT-4",
) -> Claim:
    return Claim(claim=claim, category=category, verbatim_quote=claim, subject=subject)


def make_tavily_result(
    title: str = "OpenAI Pricing",
    url: str = "https://openai.com/pricing",
    content: str = "GPT-4 Turbo is priced at $0.01 per 1K input tokens.",
    published_date: str | None = "2024-01-15",
    score: float = 0.9,
) -> dict:
    return {
        "title": title,
        "url": url,
        "content": content,
        "published_date": published_date,
        "score": score,
    }


def mock_tavily_response(results: list[dict]) -> dict:
    return {"results": results}


@pytest.fixture
def mock_tavily():
    with patch("claim_verifier._make_client") as mock_make:
        client = AsyncMock()
        client.search = AsyncMock()
        mock_make.return_value = client
        yield client


# --- Unit: _build_query ---

def test_build_query_price():
    claim = make_claim(claim="GPT-4 costs $0.03/1K tokens", category="price", subject="GPT-4")
    q = _build_query(claim)
    assert "GPT-4" in q
    assert "current price" in q


def test_build_query_version():
    claim = make_claim(claim="Python 3.12 is latest", category="version", subject="Python")
    q = _build_query(claim)
    assert "latest version" in q
    assert "Python" in q


def test_build_query_date():
    claim = make_claim(claim="Released October 2023", category="date", subject="Python 3.12")
    q = _build_query(claim)
    assert "Released October 2023" in q
    assert "Python 3.12" in q


def test_build_query_regulation():
    claim = make_claim(claim="GDPR Article 17", category="regulation", subject="GDPR")
    q = _build_query(claim)
    assert "GDPR Article 17" in q
    assert "official" in q


def test_build_query_entity():
    claim = make_claim(claim="Sam Altman is CEO of OpenAI", category="entity", subject="OpenAI")
    q = _build_query(claim)
    assert "OpenAI" in q
    assert "official source" in q


def test_build_query_fallback_unknown_category():
    claim = Claim(claim="something happened", category="entity", verbatim_quote="x", subject="X")
    q = _build_query(claim)
    assert len(q) > 0


# --- Unit: _parse_results ---

def test_parse_results_full():
    raw = [make_tavily_result()]
    results = _parse_results(raw)
    assert len(results) == 1
    r = results[0]
    assert r.title == "OpenAI Pricing"
    assert r.url == "https://openai.com/pricing"
    assert r.published_date == "2024-01-15"
    assert r.score == 0.9


def test_parse_results_empty():
    assert _parse_results([]) == []


def test_parse_results_missing_optional_fields():
    raw = [{"title": "T", "url": "https://x.com", "content": "text"}]
    results = _parse_results(raw)
    assert results[0].published_date is None
    assert results[0].score == 0.0


def test_parse_results_skips_non_dict():
    raw = ["not a dict", make_tavily_result()]
    results = _parse_results(raw)
    assert len(results) == 1


# --- Integration: verify_claim (mocked Tavily) ---

async def test_verify_returns_results_on_success(mock_tavily):
    mock_tavily.search.return_value = mock_tavily_response([make_tavily_result()])
    result = await verify_claim(make_claim())
    assert result.search_error is None
    assert len(result.results) == 1
    assert result.results[0].url == "https://openai.com/pricing"


async def test_verify_stores_query_used(mock_tavily):
    mock_tavily.search.return_value = mock_tavily_response([])
    claim = make_claim(category="price", subject="GPT-4")
    result = await verify_claim(claim)
    assert "GPT-4" in result.query_used


async def test_verify_zero_results_no_error(mock_tavily):
    mock_tavily.search.return_value = mock_tavily_response([])
    result = await verify_claim(make_claim())
    assert result.search_error is None
    assert result.results == []


async def test_verify_handles_timeout(mock_tavily):
    mock_tavily.search.side_effect = httpx.TimeoutException("timed out")
    result = await verify_claim(make_claim())
    assert result.search_error == "timeout"
    assert result.results == []


async def test_verify_handles_5xx_error(mock_tavily):
    response = httpx.Response(502, request=httpx.Request("GET", "https://tavily.com"))
    mock_tavily.search.side_effect = httpx.HTTPStatusError("bad gateway", request=response.request, response=response)
    result = await verify_claim(make_claim())
    assert result.search_error == "tavily_error:502"
    assert result.results == []


async def test_verify_handles_unexpected_exception(mock_tavily):
    mock_tavily.search.side_effect = RuntimeError("unexpected")
    result = await verify_claim(make_claim())
    assert result.search_error == "error:RuntimeError"
    assert result.results == []


async def test_verify_all_categories(mock_tavily):
    mock_tavily.search.return_value = mock_tavily_response([make_tavily_result()])
    for category in ["price", "version", "date", "regulation", "entity"]:
        claim = make_claim(category=category)
        result = await verify_claim(claim)
        assert result.search_error is None


async def test_verify_passes_raw_data_to_scorer(mock_tavily):
    """Verifier does not interpret data — just passes results through."""
    contradicting = make_tavily_result(content="GPT-4 Turbo now costs $0.01/1K tokens (changed from $0.03)")
    mock_tavily.search.return_value = mock_tavily_response([contradicting])
    result = await verify_claim(make_claim())
    assert result.results[0].snippet == contradicting["content"]
    assert result.search_error is None
