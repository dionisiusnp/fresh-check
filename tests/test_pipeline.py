from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from models import Claim, FreshnessReport, ScoredClaim


# --- Helpers ---

def make_claim(text: str = "GPT-4 costs $0.03/1K", category: str = "price", subject: str = "GPT-4") -> Claim:
    return Claim(claim=text, category=category, verbatim_quote=text, subject=subject)


def make_scored(claim: Claim, status: str = "confirmed_current") -> ScoredClaim:
    return ScoredClaim(claim=claim, status=status, reasoning="test")


@pytest.fixture(autouse=True)
def production_mode(monkeypatch):
    """Force production mode for all pipeline tests unless overridden."""
    import config
    monkeypatch.setattr(config.settings, "app_mode", config.AppMode.PRODUCTION)


# --- Production pipeline ---

async def test_pipeline_happy_path():
    c1 = make_claim("GPT-4 costs $0.03/1K", "price")
    c2 = make_claim("Python 3.12 latest", "version")

    async def mock_vas(claim):
        return make_scored(claim)

    with (
        patch("pipeline.extract_claims", new=AsyncMock(return_value=[c1, c2])),
        patch("pipeline._verify_and_score", side_effect=mock_vas),
    ):
        from pipeline import run_pipeline
        report = await run_pipeline("some LLM answer")

    assert isinstance(report, FreshnessReport)
    assert report.mode == "production"
    assert len(report.claims) == 2
    assert report.summary.total == 2
    assert report.summary.confirmed == 2
    assert report.duration_ms >= 0


async def test_pipeline_no_claims():
    with patch("pipeline.extract_claims", new=AsyncMock(return_value=[])):
        from pipeline import run_pipeline
        report = await run_pipeline("AI is helpful and easy to use.")

    assert report.claims == []
    assert report.summary.total == 0
    assert report.summary.confirmed == 0


async def test_pipeline_summary_counts_correctly():
    claims = [make_claim(f"claim {i}") for i in range(4)]
    statuses = ["confirmed_current", "contradicted", "unverifiable", "contradicted"]

    async def mock_vas(claim):
        idx = next(i for i, c in enumerate(claims) if c.claim == claim.claim)
        return make_scored(claim, statuses[idx])

    with (
        patch("pipeline.extract_claims", new=AsyncMock(return_value=claims)),
        patch("pipeline._verify_and_score", side_effect=mock_vas),
    ):
        from pipeline import run_pipeline
        report = await run_pipeline("answer")

    assert report.summary.confirmed == 1
    assert report.summary.contradicted == 2
    assert report.summary.unverifiable == 1


async def test_pipeline_partial_verifier_failure():
    """One claim's verify+score raises — rest still return; failed one becomes unverifiable."""
    c1 = make_claim("claim ok")
    c2 = make_claim("claim fail")
    call_count = 0

    async def mock_verify_and_score(claim):
        nonlocal call_count
        call_count += 1
        if claim.claim == "claim fail":
            raise RuntimeError("Tavily exploded")
        from models import VerifiedClaim
        v = VerifiedClaim(claim=claim, query_used="q", results=[], search_error=None)
        return make_scored(claim)

    with (
        patch("pipeline.extract_claims", new=AsyncMock(return_value=[c1, c2])),
        patch("pipeline._verify_and_score", new=AsyncMock(side_effect=mock_verify_and_score)),
    ):
        from pipeline import run_pipeline
        report = await run_pipeline("answer")

    assert len(report.claims) == 2
    failed = next(c for c in report.claims if c.claim.claim == "claim fail")
    ok = next(c for c in report.claims if c.claim.claim == "claim ok")
    assert failed.status == "unverifiable"
    assert "Internal error" in failed.reasoning
    assert ok.status == "confirmed_current"


async def test_pipeline_raises_on_extraction_failure():
    from exceptions import PipelineError
    with patch("pipeline.extract_claims", new=AsyncMock(side_effect=Exception("Bifrost down"))):
        from pipeline import run_pipeline
        with pytest.raises(PipelineError, match="Extraction failed"):
            await run_pipeline("some answer")


async def test_pipeline_report_contains_original_answer():
    answer = "Python 3.12 is the latest stable release."
    with patch("pipeline.extract_claims", new=AsyncMock(return_value=[])):
        from pipeline import run_pipeline
        report = await run_pipeline(answer)
    assert report.original_answer == answer


async def test_pipeline_concurrent_execution():
    """All verify+score calls run concurrently — total time << sum of individual times."""
    import asyncio
    import time

    claims = [make_claim(f"claim {i}") for i in range(4)]

    async def slow_verify_and_score(claim):
        await asyncio.sleep(0.05)
        return make_scored(claim)

    with (
        patch("pipeline.extract_claims", new=AsyncMock(return_value=claims)),
        patch("pipeline._verify_and_score", new=AsyncMock(side_effect=slow_verify_and_score)),
    ):
        from pipeline import run_pipeline
        start = time.monotonic()
        report = await run_pipeline("answer")
        elapsed = time.monotonic() - start

    assert len(report.claims) == 4
    # 4 × 50ms concurrent should finish in <150ms, not 200ms+
    assert elapsed < 0.15


# --- Demo mode ---

async def test_demo_mode_uses_fixtures(monkeypatch):
    import config
    monkeypatch.setattr(config.settings, "app_mode", config.AppMode.DEMO)

    with patch("pipeline.extract_claims") as mock_extract:
        from pipeline import run_pipeline
        report = await run_pipeline("GPT-4 Turbo costs $0.01 per 1K input tokens and $0.03 per 1K output tokens.")

    mock_extract.assert_not_called()
    assert report.mode == "demo"


async def test_demo_mode_does_not_call_apis(monkeypatch):
    import config
    monkeypatch.setattr(config.settings, "app_mode", config.AppMode.DEMO)

    with (
        patch("pipeline.extract_claims") as mock_extract,
        patch("pipeline.verify_claim") as mock_verify,
        patch("pipeline.score_claim") as mock_score,
    ):
        from pipeline import run_pipeline
        await run_pipeline("AI assistants are generally becoming more helpful.")

    mock_extract.assert_not_called()
    mock_verify.assert_not_called()
    mock_score.assert_not_called()


async def test_demo_mode_returns_freshness_report(monkeypatch):
    import config
    monkeypatch.setattr(config.settings, "app_mode", config.AppMode.DEMO)

    from pipeline import run_pipeline
    report = await run_pipeline("OpenAI was founded in 2015 and GPT-4 API costs $0.01/1K tokens.")

    assert isinstance(report, FreshnessReport)
    assert report.mode == "demo"
    assert report.summary.total == len(report.claims)


async def test_demo_mode_duration_set(monkeypatch):
    import config
    monkeypatch.setattr(config.settings, "app_mode", config.AppMode.DEMO)

    from pipeline import run_pipeline
    report = await run_pipeline("some answer")
    assert report.duration_ms >= 0
