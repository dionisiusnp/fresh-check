from __future__ import annotations

from models import Claim, ClaimSummary, FreshnessReport, ScoredClaim

_FIXTURES: list[dict] = [
    {
        "id": "outdated_pricing",
        "label": "LLM Pricing (Outdated)",
        "keywords": ["gpt-4", "0.03", "0.01", "per 1k", "tokens", "pricing"],
        "llm_answer": "GPT-4 Turbo costs $0.01 per 1K input tokens and $0.03 per 1K output tokens.",
        "claims": [
            ScoredClaim(
                claim=Claim(
                    claim="GPT-4 Turbo costs $0.01 per 1K input tokens",
                    category="price",
                    verbatim_quote="GPT-4 Turbo costs $0.01 per 1K input tokens",
                    subject="GPT-4 Turbo",
                ),
                status="contradicted",
                reasoning="OpenAI updated GPT-4 Turbo pricing in 2024; current rate differs.",
                contradicting_evidence="GPT-4 Turbo is now priced at $0.005 per 1K input tokens.",
                source_url="https://openai.com/pricing",
                source_date="2026-03-01",
            ),
        ],
    },
    {
        "id": "correct_version",
        "label": "Python Version (Current)",
        "keywords": ["python", "3.12", "stable", "release"],
        "llm_answer": "Python 3.12 is the latest stable release with significant performance improvements.",
        "claims": [
            ScoredClaim(
                claim=Claim(
                    claim="Python 3.12 is the latest stable release",
                    category="version",
                    verbatim_quote="Python 3.12 is the latest stable release",
                    subject="Python",
                ),
                status="confirmed_current",
                reasoning="Python.org confirms 3.12 as the current stable branch.",
                source_url="https://www.python.org/downloads/",
                source_date="2026-01-10",
            ),
        ],
    },
    {
        "id": "no_claims",
        "label": "Opinion Only (No Claims)",
        "keywords": ["helpful", "easier", "general", "ai assistant"],
        "llm_answer": "AI assistants are generally becoming more helpful and easier to use.",
        "claims": [],
    },
    {
        "id": "mixed_claims",
        "label": "Mixed: Some Stale, Some Current",
        "keywords": ["openai", "founded", "2015", "gpt-4", "0.01"],
        "llm_answer": "OpenAI was founded in 2015 and GPT-4 API costs $0.01/1K tokens.",
        "claims": [
            ScoredClaim(
                claim=Claim(
                    claim="OpenAI was founded in 2015",
                    category="date",
                    verbatim_quote="OpenAI was founded in 2015",
                    subject="OpenAI",
                ),
                status="confirmed_current",
                reasoning="Multiple sources confirm OpenAI was incorporated in December 2015.",
                source_url="https://en.wikipedia.org/wiki/OpenAI",
                source_date="2026-05-01",
            ),
            ScoredClaim(
                claim=Claim(
                    claim="GPT-4 API costs $0.01/1K tokens",
                    category="price",
                    verbatim_quote="GPT-4 API costs $0.01/1K tokens",
                    subject="GPT-4",
                ),
                status="contradicted",
                reasoning="OpenAI pricing page shows updated rates that differ from this claim.",
                contradicting_evidence="GPT-4 Turbo input is now $0.005/1K tokens.",
                source_url="https://openai.com/pricing",
                source_date="2026-03-01",
            ),
        ],
    },
    {
        "id": "unverifiable",
        "label": "Internal Fact (Unverifiable)",
        "keywords": ["acme", "47", "engineers", "ml team", "internal"],
        "llm_answer": "Acme Corp has 47 engineers in their ML team.",
        "claims": [
            ScoredClaim(
                claim=Claim(
                    claim="Acme Corp has 47 engineers in their ML team",
                    category="entity",
                    verbatim_quote="Acme Corp has 47 engineers in their ML team",
                    subject="Acme Corp",
                ),
                status="unverifiable",
                reasoning="No public sources found for internal team composition.",
            ),
        ],
    },
]


def _score(fixture: dict) -> ClaimSummary:
    claims = fixture["claims"]
    return ClaimSummary(
        total=len(claims),
        confirmed=sum(1 for c in claims if c.status == "confirmed_current"),
        contradicted=sum(1 for c in claims if c.status == "contradicted"),
        unverifiable=sum(1 for c in claims if c.status == "unverifiable"),
    )


def _match_fixture(text: str) -> dict:
    text_lower = text.lower()
    best: dict | None = None
    best_hits = 0

    for f in _FIXTURES:
        hits = sum(1 for kw in f["keywords"] if kw in text_lower)
        if hits > best_hits:
            best_hits = hits
            best = f

    return best or _FIXTURES[0]


def get_demo_result(llm_answer: str) -> FreshnessReport:
    fixture = _match_fixture(llm_answer)
    return FreshnessReport(
        original_answer=llm_answer,
        claims=fixture["claims"],
        summary=_score(fixture),
        mode="demo",
        duration_ms=0,
    )


def get_all_fixtures() -> list[dict]:
    return [{"id": f["id"], "label": f["label"], "llm_answer": f["llm_answer"]} for f in _FIXTURES]
