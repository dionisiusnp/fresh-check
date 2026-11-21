from __future__ import annotations

import asyncio
import logging
import time

from claim_extractor import extract_claims
from claim_verifier import verify_claim
from config import AppMode, settings
from exceptions import PipelineError
from freshness_scorer import score_claim
from models import ClaimSummary, FreshnessReport, ScoredClaim

logger = logging.getLogger(__name__)


async def _verify_and_score(claim) -> ScoredClaim:
    verified = await verify_claim(claim)
    return await score_claim(verified)


async def _run_production(llm_answer: str) -> list[ScoredClaim]:
    try:
        claims = await extract_claims(llm_answer)
    except Exception as e:
        raise PipelineError(f"Extraction failed: {e}") from e

    if not claims:
        return []

    results = await asyncio.gather(
        *[_verify_and_score(c) for c in claims],
        return_exceptions=True,
    )

    scored: list[ScoredClaim] = []
    for claim, result in zip(claims, results):
        if isinstance(result, BaseException):
            logger.warning("verify+score failed for claim %r: %s", claim.claim, result)
            scored.append(ScoredClaim(
                claim=claim,
                status="unverifiable",
                reasoning=f"Internal error: {type(result).__name__}",
            ))
        else:
            scored.append(result)

    return scored


def _build_summary(scored: list[ScoredClaim]) -> ClaimSummary:
    return ClaimSummary(
        total=len(scored),
        confirmed=sum(1 for c in scored if c.status == "confirmed_current"),
        contradicted=sum(1 for c in scored if c.status == "contradicted"),
        unverifiable=sum(1 for c in scored if c.status == "unverifiable"),
    )


async def run_pipeline(llm_answer: str) -> FreshnessReport:
    start = time.monotonic()

    if settings.app_mode == AppMode.DEMO:
        from demo.fixtures import get_demo_result
        report = get_demo_result(llm_answer)
        report.duration_ms = int((time.monotonic() - start) * 1000)
        return report

    scored = await _run_production(llm_answer)
    duration_ms = int((time.monotonic() - start) * 1000)

    return FreshnessReport(
        original_answer=llm_answer,
        claims=scored,
        summary=_build_summary(scored),
        mode="production",
        duration_ms=duration_ms,
    )
