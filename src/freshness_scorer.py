from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from openai import AsyncOpenAI

from config import settings
from exceptions import ScoringError
from models import ClaimStatus, ScoredClaim, SearchResult, VerifiedClaim

logger = logging.getLogger(__name__)

SOURCE_MAX_AGE_YEARS = 2

SCORE_PROMPT = """Given this claim and web search results, determine if the claim is currently accurate.

Claim: {claim}
Category: {category}

Search Results:
{search_results}

Rules:
- confirmed_current: results clearly support the claim as still accurate
- contradicted: results contain specific contradicting evidence (different price, version, date, etc.)
- unverifiable: results are irrelevant, too old, or insufficient to make a verdict
- When uncertain, choose unverifiable — do not force a verdict
- Opinions and subjective statements must be unverifiable

Return JSON only, no markdown fences:
{{
  "status": "confirmed_current|contradicted|unverifiable",
  "reasoning": "one sentence explanation",
  "contradicting_evidence": "exact quote from results (only if contradicted, else null)",
  "source_url": "URL of primary evidence (null if unverifiable)"
}}"""


def _make_client() -> AsyncOpenAI:
    return AsyncOpenAI(
        api_key=settings.bifrost_api_key or "placeholder",
        base_url=settings.bifrost_base_url + "/v1",
    )


def _format_results(results: list[SearchResult]) -> str:
    if not results:
        return "(no results)"
    lines: list[str] = []
    for i, r in enumerate(results, 1):
        date_str = f" [{r.published_date}]" if r.published_date else ""
        lines.append(f"{i}. {r.title}{date_str}\n   URL: {r.url}\n   {r.snippet}")
    return "\n\n".join(lines)


def _is_too_old(published_date: str | None) -> bool:
    if not published_date:
        return False
    try:
        pub = datetime.fromisoformat(published_date.replace("Z", "+00:00"))
        if pub.tzinfo is None:
            pub = pub.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        age_years = (now - pub).days / 365.25
        return age_years > SOURCE_MAX_AGE_YEARS
    except (ValueError, TypeError):
        return False


def _all_results_too_old(results: list[SearchResult]) -> bool:
    if not results:
        return False
    dated = [r for r in results if r.published_date]
    if not dated:
        return False
    return all(_is_too_old(r.published_date) for r in dated)


def _parse_verdict(raw: str) -> dict:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    return json.loads(raw)


def _unverifiable(claim_text: str, reasoning: str) -> ScoredClaim:
    from models import Claim
    # Reconstruct minimal Claim for standalone use — normally VerifiedClaim carries original
    return ScoredClaim(
        claim=Claim(claim=claim_text, category="entity", verbatim_quote="", subject=""),
        status="unverifiable",
        reasoning=reasoning,
    )


async def score_claim(verified: VerifiedClaim) -> ScoredClaim:
    claim = verified.claim

    # Propagate search errors as unverifiable
    if verified.search_error:
        return ScoredClaim(
            claim=claim,
            status="unverifiable",
            reasoning=f"Search failed: {verified.search_error}",
            search_error=verified.search_error,
        )

    # No results → unverifiable
    if not verified.results:
        return ScoredClaim(
            claim=claim,
            status="unverifiable",
            reasoning="No search results found.",
        )

    # All dated results too old → unverifiable
    if _all_results_too_old(verified.results):
        return ScoredClaim(
            claim=claim,
            status="unverifiable",
            reasoning=f"All sources older than {SOURCE_MAX_AGE_YEARS} years.",
        )

    formatted = _format_results(verified.results)
    prompt = SCORE_PROMPT.format(
        claim=claim.claim,
        category=claim.category,
        search_results=formatted,
    )

    client = _make_client()
    try:
        response = await client.chat.completions.create(
            model=settings.llm_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
        )
    except Exception as e:
        logger.warning("Bifrost scorer call failed for claim %r: %s", claim.claim, e)
        return ScoredClaim(
            claim=claim,
            status="unverifiable",
            reasoning=f"Scorer LLM call failed: {type(e).__name__}",
        )

    raw = response.choices[0].message.content or ""

    try:
        data = _parse_verdict(raw)
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning("Scorer returned invalid JSON for claim %r: %s", claim.claim, e)
        return ScoredClaim(
            claim=claim,
            status="unverifiable",
            reasoning="Scorer returned invalid response.",
        )

    status: ClaimStatus = data.get("status", "unverifiable")
    if status not in ("confirmed_current", "contradicted", "unverifiable"):
        status = "unverifiable"

    # Find source date from result matching source_url
    source_url: str | None = data.get("source_url")
    source_date: str | None = None
    if source_url:
        for r in verified.results:
            if r.url == source_url:
                source_date = r.published_date
                break

    return ScoredClaim(
        claim=claim,
        status=status,
        reasoning=data.get("reasoning", ""),
        contradicting_evidence=data.get("contradicting_evidence"),
        source_url=source_url,
        source_date=source_date,
    )
