from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from claim_extractor import _deduplicate, _parse_claims, _truncate, extract_claims
from exceptions import ExtractionError
from models import Claim


# --- Unit: _truncate ---

def test_truncate_short_input_unchanged():
    text = "hello world"
    result, truncated = _truncate(text)
    assert result == text
    assert truncated is False


def test_truncate_long_input():
    text = " ".join(["word"] * 4000)
    result, truncated = _truncate(text)
    assert truncated is True
    assert len(result.split()) == 3000


# --- Unit: _parse_claims ---

def _make_raw(items: list[dict]) -> str:
    return json.dumps(items)


def test_parse_valid_price_claim():
    raw = _make_raw([{
        "claim": "GPT-4 costs $0.03/1K tokens",
        "category": "price",
        "verbatim_quote": "GPT-4 costs $0.03 per 1K tokens",
        "subject": "GPT-4",
    }])
    claims = _parse_claims(raw)
    assert len(claims) == 1
    assert claims[0].category == "price"
    assert claims[0].subject == "GPT-4"


def test_parse_multiple_claims():
    raw = _make_raw([
        {"claim": "Python 3.12 released", "category": "version", "verbatim_quote": "Python 3.12", "subject": "Python"},
        {"claim": "Released October 2023", "category": "date", "verbatim_quote": "October 2023", "subject": "Python 3.12"},
    ])
    claims = _parse_claims(raw)
    assert len(claims) == 2


def test_parse_empty_array():
    claims = _parse_claims("[]")
    assert claims == []


def test_parse_strips_markdown_fences():
    raw = "```json\n[]\n```"
    claims = _parse_claims(raw)
    assert claims == []


def test_parse_invalid_json_raises():
    with pytest.raises(ExtractionError, match="invalid JSON"):
        _parse_claims("not json at all")


def test_parse_non_array_raises():
    with pytest.raises(ExtractionError, match="Expected JSON array"):
        _parse_claims('{"claim": "something"}')


def test_parse_skips_unknown_category():
    raw = _make_raw([{
        "claim": "Something happened",
        "category": "unknown_category",
        "verbatim_quote": "Something happened",
        "subject": "Something",
    }])
    claims = _parse_claims(raw)
    assert claims == []


def test_parse_skips_empty_claim_string():
    raw = _make_raw([{
        "claim": "",
        "category": "price",
        "verbatim_quote": "GPT-4 costs $0.03",
        "subject": "GPT-4",
    }])
    claims = _parse_claims(raw)
    assert claims == []


def test_parse_skips_non_dict_items():
    raw = json.dumps(["not a dict", {"claim": "valid claim", "category": "price", "verbatim_quote": "v", "subject": "s"}])
    claims = _parse_claims(raw)
    assert len(claims) == 1


# --- Unit: _deduplicate ---

def test_deduplicate_removes_exact_duplicates():
    c1 = Claim("GPT-4 costs $0.03/1K tokens", "price", "GPT-4 costs $0.03", "GPT-4")
    c2 = Claim("GPT-4 costs $0.03/1K tokens", "price", "GPT-4 costs $0.03", "GPT-4")
    result = _deduplicate([c1, c2])
    assert len(result) == 1


def test_deduplicate_case_insensitive():
    c1 = Claim("gpt-4 costs $0.03/1k tokens", "price", "q1", "GPT-4")
    c2 = Claim("GPT-4 COSTS $0.03/1K TOKENS", "price", "q2", "GPT-4")
    result = _deduplicate([c1, c2])
    assert len(result) == 1


def test_deduplicate_keeps_different_claims():
    c1 = Claim("Python 3.12", "version", "v1", "Python")
    c2 = Claim("Released October 2023", "date", "v2", "Python 3.12")
    result = _deduplicate([c1, c2])
    assert len(result) == 2


# --- Integration: extract_claims (mocked Bifrost) ---

def _mock_response(content: str) -> MagicMock:
    msg = MagicMock()
    msg.content = content
    choice = MagicMock()
    choice.message = msg
    response = MagicMock()
    response.choices = [choice]
    return response


@pytest.fixture
def mock_bifrost():
    with patch("claim_extractor._make_client") as mock_make:
        client = AsyncMock()
        client.chat.completions.create = AsyncMock()
        mock_make.return_value = client
        yield client


async def test_extract_price_claim(mock_bifrost):
    mock_bifrost.chat.completions.create.return_value = _mock_response(_make_raw([{
        "claim": "GPT-4 costs $0.03/1K tokens",
        "category": "price",
        "verbatim_quote": "GPT-4 costs $0.03 per 1K tokens",
        "subject": "GPT-4",
    }]))
    claims = await extract_claims("GPT-4 costs $0.03 per 1K tokens.")
    assert len(claims) == 1
    assert claims[0].category == "price"


async def test_extract_multiple_claims(mock_bifrost):
    mock_bifrost.chat.completions.create.return_value = _mock_response(_make_raw([
        {"claim": "Python 3.12 is latest", "category": "version", "verbatim_quote": "Python 3.12", "subject": "Python"},
        {"claim": "Released October 2023", "category": "date", "verbatim_quote": "October 2023", "subject": "Python 3.12"},
    ]))
    claims = await extract_claims("Python 3.12, released October 2023, is the latest stable release.")
    assert len(claims) == 2


async def test_extract_returns_empty_for_opinion_only(mock_bifrost):
    mock_bifrost.chat.completions.create.return_value = _mock_response("[]")
    claims = await extract_claims("GPT-4 is the best model available.")
    assert claims == []


async def test_extract_returns_empty_for_vague_claim(mock_bifrost):
    mock_bifrost.chat.completions.create.return_value = _mock_response("[]")
    claims = await extract_claims("AI is becoming more expensive over time.")
    assert claims == []


async def test_extract_empty_input_skips_api():
    claims = await extract_claims("")
    assert claims == []


async def test_extract_whitespace_only_skips_api():
    claims = await extract_claims("   \n\t  ")
    assert claims == []


async def test_extract_deduplicates_duplicate_claims(mock_bifrost):
    mock_bifrost.chat.completions.create.return_value = _mock_response(_make_raw([
        {"claim": "GPT-4 costs $0.03/1K tokens", "category": "price", "verbatim_quote": "v1", "subject": "GPT-4"},
        {"claim": "GPT-4 costs $0.03/1K tokens", "category": "price", "verbatim_quote": "v2", "subject": "GPT-4"},
    ]))
    claims = await extract_claims("GPT-4 costs $0.03/1K tokens. Also, GPT-4 costs $0.03/1K tokens.")
    assert len(claims) == 1


async def test_extract_handles_mixed_content(mock_bifrost):
    mock_bifrost.chat.completions.create.return_value = _mock_response(_make_raw([
        {"claim": "Anthropic charges $3/1M tokens for Sonnet", "category": "price", "verbatim_quote": "$3/1M tokens", "subject": "Claude Sonnet"},
    ]))
    claims = await extract_claims("Claude is fast (Anthropic charges $3/1M tokens for Sonnet).")
    assert len(claims) == 1
    assert claims[0].category == "price"


async def test_extract_raises_on_bifrost_failure(mock_bifrost):
    mock_bifrost.chat.completions.create.side_effect = Exception("connection refused")
    with pytest.raises(ExtractionError, match="Bifrost call failed"):
        await extract_claims("Some answer with facts.")


async def test_extract_raises_on_invalid_json_response(mock_bifrost):
    mock_bifrost.chat.completions.create.return_value = _mock_response("I cannot process this request.")
    with pytest.raises(ExtractionError, match="invalid JSON"):
        await extract_claims("Some answer.")


async def test_extract_non_english_input(mock_bifrost):
    mock_bifrost.chat.completions.create.return_value = _mock_response(_make_raw([{
        "claim": "Python 3.12 is latest stable version",
        "category": "version",
        "verbatim_quote": "Python 3.12",
        "subject": "Python",
    }]))
    claims = await extract_claims("Python 3.12 adalah versi stabil terbaru dengan peningkatan performa signifikan.")
    assert len(claims) == 1


async def test_extract_truncates_long_input(mock_bifrost):
    long_answer = " ".join(["word"] * 5000)
    mock_bifrost.chat.completions.create.return_value = _mock_response("[]")
    await extract_claims(long_answer)
    call_args = mock_bifrost.chat.completions.create.call_args
    prompt_text = call_args.kwargs["messages"][0]["content"]
    # Truncated to 3000 words, so prompt word count should be well under 5000
    assert len(prompt_text.split()) < 4000
