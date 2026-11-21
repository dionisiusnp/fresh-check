from __future__ import annotations
from dataclasses import dataclass, field
from typing import Literal


ClaimStatus = Literal["confirmed_current", "contradicted", "unverifiable"]
ClaimCategory = Literal["price", "version", "date", "regulation", "entity"]


@dataclass
class Claim:
    claim: str
    category: ClaimCategory
    verbatim_quote: str
    subject: str


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str
    published_date: str | None = None
    score: float = 0.0


@dataclass
class VerifiedClaim:
    claim: Claim
    query_used: str
    results: list[SearchResult] = field(default_factory=list)
    search_error: str | None = None


@dataclass
class ScoredClaim:
    claim: Claim
    status: ClaimStatus
    reasoning: str
    contradicting_evidence: str | None = None
    source_url: str | None = None
    source_date: str | None = None
    search_error: str | None = None


@dataclass
class ClaimSummary:
    total: int
    confirmed: int
    contradicted: int
    unverifiable: int


@dataclass
class FreshnessReport:
    original_answer: str
    claims: list[ScoredClaim]
    summary: ClaimSummary
    mode: str
    duration_ms: int
