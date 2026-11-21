from __future__ import annotations

import html
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from config import settings
from demo.fixtures import get_all_fixtures
from exceptions import PipelineError
from models import FreshnessReport, ScoredClaim
from pipeline import run_pipeline

app = FastAPI(title="FreshCheck")
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")


class CheckRequest(BaseModel):
    llm_answer: str


def _annotate_answer(original: str, claims: list[ScoredClaim]) -> str:
    STATUS_CLASS = {
        "confirmed_current": "fc-confirmed",
        "contradicted": "fc-contradicted",
        "unverifiable": "fc-unverifiable",
    }
    STATUS_LABEL = {
        "confirmed_current": "✓ Confirmed",
        "contradicted": "✗ Contradicted",
        "unverifiable": "? Unverifiable",
    }

    # Sort longest verbatim_quote first — longest claims get priority for overlap resolution
    sorted_claims = sorted(
        [c for c in claims if c.claim.verbatim_quote],
        key=lambda c: len(c.claim.verbatim_quote),
        reverse=True,
    )

    # Find non-overlapping positions in the ORIGINAL (unescaped) text
    segments: list[tuple[int, int, ScoredClaim]] = []
    occupied: list[tuple[int, int]] = []

    for scored in sorted_claims:
        quote = scored.claim.verbatim_quote
        pos = original.find(quote)
        if pos == -1:
            continue
        end = pos + len(quote)
        # Skip if overlaps with an already-claimed segment
        if any(s <= pos < e or s < end <= e or pos <= s < end for s, e in occupied):
            continue
        occupied.append((pos, end))
        segments.append((pos, end, scored))

    # Sort segments by start position for sequential assembly
    segments.sort(key=lambda x: x[0])

    parts: list[str] = []
    cursor = 0

    for start, end, scored in segments:
        parts.append(html.escape(original[cursor:start]))

        css = STATUS_CLASS.get(scored.status, "fc-unverifiable")
        label = STATUS_LABEL.get(scored.status, "?")
        tooltip = html.escape(scored.reasoning or "")
        quote_escaped = html.escape(original[start:end])
        source = ""
        if scored.source_url and scored.status == "contradicted":
            source = f' <a href="{html.escape(scored.source_url)}" target="_blank" class="fc-source-link">source ↗</a>'

        parts.append(
            f'<mark class="{css}" title="{tooltip}">'
            f'{quote_escaped}'
            f'<span class="fc-badge">{label}</span>'
            f'{source}'
            f'</mark>'
        )
        cursor = end

    parts.append(html.escape(original[cursor:]))
    return "".join(parts).replace("\n", "<br>")


def _report_to_json(report: FreshnessReport) -> dict:
    return {
        "mode": report.mode,
        "duration_ms": report.duration_ms,
        "original_answer": report.original_answer,
        "annotated_answer": _annotate_answer(report.original_answer, report.claims),
        "summary": {
            "total": report.summary.total,
            "confirmed": report.summary.confirmed,
            "contradicted": report.summary.contradicted,
            "unverifiable": report.summary.unverifiable,
        },
        "claims": [
            {
                "claim": c.claim.claim,
                "category": c.claim.category,
                "verbatim_quote": c.claim.verbatim_quote,
                "subject": c.claim.subject,
                "status": c.status,
                "reasoning": c.reasoning,
                "contradicting_evidence": c.contradicting_evidence,
                "source_url": c.source_url,
                "source_date": c.source_date,
            }
            for c in report.claims
        ],
    }


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "mode": settings.app_mode.value,
            "fixtures": get_all_fixtures(),
        },
    )


@app.post("/check")
async def check(body: CheckRequest):
    if not body.llm_answer or not body.llm_answer.strip():
        return JSONResponse({"error": "llm_answer is required"}, status_code=422)
    try:
        report = await run_pipeline(body.llm_answer)
        return _report_to_json(report)
    except PipelineError as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/health")
async def health():
    return {"status": "ok", "mode": settings.app_mode.value}
