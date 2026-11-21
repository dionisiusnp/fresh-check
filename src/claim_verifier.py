from __future__ import annotations

import asyncio
import logging
import time

import httpx
from tavily import AsyncTavilyClient

from config import AppMode, settings
from exceptions import VerificationError
from models import Claim, SearchResult, VerifiedClaim

logger = logging.getLogger(__name__)

QUERY_TEMPLATES: dict[str, str] = {
    "price":      "current price {subject} {claim}",
    "version":    "latest version {subject} release notes",
    "date":       "{claim} {subject} official announcement",
    "regulation": "{claim} official text status",
    "entity":     "{subject} {claim} official source",
}

# Simple token bucket for production rate limiting
_rate_lock = asyncio.Lock()
_tokens: float = 0.0
_last_refill: float = 0.0


def _build_query(claim: Claim) -> str:
    template = QUERY_TEMPLATES.get(claim.category, "{claim} {subject}")
    return template.format(claim=claim.claim, subject=claim.subject).strip()


def _make_client() -> AsyncTavilyClient:
    return AsyncTavilyClient(api_key=settings.tavily_api_key)


def _parse_results(raw: list[dict]) -> list[SearchResult]:
    results: list[SearchResult] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        results.append(SearchResult(
            title=item.get("title", ""),
            url=item.get("url", ""),
            snippet=item.get("content", ""),
            published_date=item.get("published_date"),
            score=float(item.get("score", 0.0)),
        ))
    return results


async def _acquire_rate_limit_token() -> None:
    """Token bucket: refills at tavily_rate_limit_rpm tokens per minute."""
    global _tokens, _last_refill

    async with _rate_lock:
        now = time.monotonic()
        rpm = settings.tavily_rate_limit_rpm
        elapsed = now - _last_refill

        if _last_refill == 0.0:
            _tokens = float(rpm)
            _last_refill = now
        else:
            refill = elapsed * (rpm / 60.0)
            _tokens = min(float(rpm), _tokens + refill)
            _last_refill = now

        if _tokens < 1.0:
            wait = (1.0 - _tokens) / (rpm / 60.0)
            logger.debug("Rate limit: waiting %.2fs", wait)
            await asyncio.sleep(wait)
            _tokens = 0.0
        else:
            _tokens -= 1.0


async def verify_claim(claim: Claim) -> VerifiedClaim:
    query = _build_query(claim)

    if settings.app_mode == AppMode.PRODUCTION:
        await _acquire_rate_limit_token()

    client = _make_client()

    try:
        response = await client.search(
            query=query,
            max_results=settings.tavily_max_results,
            include_answer=False,
        )
    except httpx.TimeoutException:
        logger.warning("Tavily timeout for claim: %s", claim.claim)
        return VerifiedClaim(claim=claim, query_used=query, results=[], search_error="timeout")
    except httpx.HTTPStatusError as e:
        code = e.response.status_code
        logger.warning("Tavily HTTP error %d for claim: %s", code, claim.claim)
        return VerifiedClaim(claim=claim, query_used=query, results=[], search_error=f"tavily_error:{code}")
    except Exception as e:
        logger.warning("Tavily unexpected error for claim %r: %s", claim.claim, e)
        return VerifiedClaim(claim=claim, query_used=query, results=[], search_error=f"error:{type(e).__name__}")

    raw_results: list[dict] = response.get("results", [])
    results = _parse_results(raw_results)

    return VerifiedClaim(claim=claim, query_used=query, results=results, search_error=None)
