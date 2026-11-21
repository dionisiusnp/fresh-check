from __future__ import annotations

import json
import logging

from openai import AsyncOpenAI

from config import settings
from exceptions import ExtractionError
from models import Claim

logger = logging.getLogger(__name__)

MAX_INPUT_WORDS = 3000

EXTRACT_PROMPT = """Extract all verifiable factual claims from the AI answer below.

Rules:
- Only include objectively verifiable facts: prices, version numbers, dates, named regulations, named entity facts
- Skip opinions, recommendations, and subjective statements
- Skip vague claims without specific verifiable values (e.g. "AI is becoming more expensive")
- If no verifiable claims exist, return empty array

Return JSON array only, no markdown fences:
[
  {{
    "claim": "concise restatement of the claim",
    "category": "price|version|date|regulation|entity",
    "verbatim_quote": "exact quote from the answer",
    "subject": "what or who the claim is about"
  }}
]

Answer:
{llm_answer}"""


def _make_client() -> AsyncOpenAI:
    return AsyncOpenAI(
        api_key=settings.bifrost_api_key or "placeholder",
        base_url=settings.bifrost_base_url + "/v1",
    )


def _truncate(text: str) -> tuple[str, bool]:
    words = text.split()
    if len(words) <= MAX_INPUT_WORDS:
        return text, False
    return " ".join(words[:MAX_INPUT_WORDS]), True


def _parse_claims(raw: str) -> list[Claim]:
    raw = raw.strip()
    # Strip markdown fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ExtractionError(f"LLM returned invalid JSON: {e}. Raw: {raw[:200]}")

    if not isinstance(data, list):
        raise ExtractionError(f"Expected JSON array, got {type(data).__name__}")

    valid_categories = {"price", "version", "date", "regulation", "entity"}
    claims: list[Claim] = []

    for i, item in enumerate(data):
        if not isinstance(item, dict):
            logger.warning("Skipping non-dict item at index %d", i)
            continue

        category = item.get("category", "").lower()
        if category not in valid_categories:
            logger.warning("Skipping claim with unknown category %r at index %d", category, i)
            continue

        claim = item.get("claim", "").strip()
        verbatim = item.get("verbatim_quote", "").strip()
        subject = item.get("subject", "").strip()

        if not claim:
            logger.warning("Skipping empty claim at index %d", i)
            continue

        claims.append(Claim(
            claim=claim,
            category=category,  # type: ignore[arg-type]
            verbatim_quote=verbatim,
            subject=subject,
        ))

    return claims


def _deduplicate(claims: list[Claim]) -> list[Claim]:
    seen: set[str] = set()
    unique: list[Claim] = []
    for c in claims:
        key = c.claim.lower().strip()
        if key not in seen:
            seen.add(key)
            unique.append(c)
    return unique


async def extract_claims(llm_answer: str) -> list[Claim]:
    if not llm_answer or not llm_answer.strip():
        return []

    text, was_truncated = _truncate(llm_answer)
    if was_truncated:
        logger.warning("Input truncated from %d to %d words", len(llm_answer.split()), MAX_INPUT_WORDS)

    prompt = EXTRACT_PROMPT.format(llm_answer=text)
    client = _make_client()

    try:
        response = await client.chat.completions.create(
            model=settings.llm_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
        )
    except Exception as e:
        raise ExtractionError(f"Bifrost call failed: {e}") from e

    raw = response.choices[0].message.content or ""
    claims = _parse_claims(raw)
    return _deduplicate(claims)
