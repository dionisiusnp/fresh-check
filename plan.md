# FreshCheck — Build Plan

> Stale-claim detector for LLM answers.
> Flow: LLM answer → extract claims (Bifrost) → verify each (Tavily) → score per-claim → annotated output.

---

## Project Structure

```
fresh-check/
├── src/
│   ├── claim_extractor.py     # Bifrost LLM call → structured claim list
│   ├── claim_verifier.py      # Tavily search per claim → evidence
│   ├── freshness_scorer.py    # evidence → confirmed|contradicted|unverifiable
│   ├── pipeline.py            # orchestrates all three
│   └── config.py              # env + mode switch (demo|production)
├── ui/
│   ├── app.py                 # FastAPI server
│   └── templates/
│       └── index.html         # input form + annotated result view
├── tests/
│   ├── test_extractor.py
│   ├── test_verifier.py
│   ├── test_scorer.py
│   └── test_pipeline.py       # end-to-end
├── demo/
│   └── fixtures.py            # pre-baked answers + expected outcomes
├── .env.example
├── requirements.txt
└── README.md
```

---

## Phase 1 — Setup

### 1.1 Dependencies

```
# requirements.txt
httpx
fastapi
uvicorn[standard]
python-dotenv
tavily-python
openai            # Bifrost-compatible client
jinja2            # HTML templates
pytest
pytest-asyncio
```

### 1.2 Environment Variables

```bash
# .env.example
APP_MODE=demo                      # demo | production

# Bifrost
BIFROST_BASE_URL=http://localhost:8080
BIFROST_API_KEY=your_key_here
LLM_MODEL=gpt-4o-mini

# Tavily
TAVILY_API_KEY=your_key_here
TAVILY_MAX_RESULTS=3               # turunkan ke 1 saat dev

# Rate limiting (production)
TAVILY_RATE_LIMIT_RPM=10
```

### 1.3 Config Module

**File:** `src/config.py`

```python
from enum import Enum
from pydantic_settings import BaseSettings

class AppMode(str, Enum):
    DEMO = "demo"
    PRODUCTION = "production"

class Settings(BaseSettings):
    app_mode: AppMode = AppMode.DEMO
    bifrost_base_url: str = "http://localhost:8080"
    bifrost_api_key: str = ""
    llm_model: str = "gpt-4o-mini"
    tavily_api_key: str = ""
    tavily_max_results: int = 3
    tavily_rate_limit_rpm: int = 10

    class Config:
        env_file = ".env"

settings = Settings()
```

### 1.4 Bifrost Setup

```bash
# Local (Docker) — paling cepat
docker run -p 8080:8080 maximhq/bifrost

# Verifikasi
curl http://localhost:8080/health
```

---

## Phase 2 — Claim Extractor

**File:** `src/claim_extractor.py`

### Tanggung Jawab
Terima teks jawaban LLM → return list klaim faktual yang bisa diverifikasi secara objektif.

### Kategori Klaim (scope)
- `price` — harga, biaya, tarif
- `version` — nomor versi software/API
- `date` — tanggal, deadline, timeline
- `regulation` — nama regulasi, kebijakan, hukum
- `entity` — fakta entitas bernama (CEO, jumlah karyawan, funding, dsb)

### Prompt Template

```python
EXTRACT_PROMPT = """
Extract all verifiable factual claims from the AI answer below.

Rules:
- Only include objectively verifiable facts (prices, versions, dates, named regulations, named entity facts)
- Skip opinions, recommendations, and subjective statements
- Skip vague claims without specific verifiable values
- If no verifiable claims exist, return empty array

Return JSON array only:
[
  {
    "claim": "concise restatement of the claim",
    "category": "price|version|date|regulation|entity",
    "verbatim_quote": "exact quote from the answer",
    "subject": "what/who the claim is about"
  }
]

Answer:
{llm_answer}
"""
```

### Output Type

```python
@dataclass
class Claim:
    claim: str
    category: str           # price|version|date|regulation|entity
    verbatim_quote: str
    subject: str
```

### Cases

| Case | Input | Expected Output |
|------|-------|-----------------|
| Positive | "GPT-4 costs $0.03/1K tokens" | `[{claim: "GPT-4 costs $0.03/1K input tokens", category: "price", ...}]` |
| Multiple claims | "Python 3.12 released Oct 2023, successor to 3.11" | 2 claims: version + date |
| Negative — opinion | "GPT-4 is the best model available" | `[]` — no verifiable claim |
| Negative — vague | "AI is becoming more expensive" | `[]` — no specific value |
| Edge — mixed | "Claude is fast (Anthropic charges $3/1M tokens for Sonnet)" | 1 claim: price only |
| Edge — empty input | `""` | `[]` |
| Edge — non-English | Jawaban Bahasa Indonesia | Harus tetap ekstrak klaim (prompt multilingual) |
| Edge — LLM returns invalid JSON | Bifrost timeout/hallucinated format | Raise `ExtractionError`, jangan crash pipeline |

---

## Phase 3 — Claim Verifier

**File:** `src/claim_verifier.py`

### Tanggung Jawab
Untuk tiap klaim → jalankan Tavily search → return bukti (snippets + metadata).

### Query Construction

```python
QUERY_TEMPLATES = {
    "price":      "current price {subject} {claim}",
    "version":    "latest version {subject} release notes",
    "date":       "{claim} {subject} official announcement",
    "regulation": "{claim} official text status",
    "entity":     "{subject} {claim} official source",
}

def build_query(claim: Claim) -> str:
    template = QUERY_TEMPLATES.get(claim.category, "{claim} {subject}")
    return template.format(claim=claim.claim, subject=claim.subject)
```

### Output Type

```python
@dataclass
class SearchResult:
    title: str
    url: str
    published_date: str | None
    snippet: str
    score: float            # Tavily relevance score

@dataclass
class VerifiedClaim:
    claim: Claim
    query_used: str
    results: list[SearchResult]
    search_error: str | None   # None jika berhasil
```

### Cases

| Case | Scenario | Expected Behaviour |
|------|----------|--------------------|
| Positive | Klaim valid, Tavily return hasil relevan | `results` terisi, `search_error=None` |
| Negative | Tavily return 0 results | `results=[]`, `search_error=None` — scorer handle sebagai unverifiable |
| Edge — timeout | Tavily API timeout | `search_error="timeout"`, pipeline lanjut ke klaim berikutnya |
| Edge — rate limit | >10 req/menit (production) | Throttle otomatis, jangan raise ke user |
| Edge — Tavily error 5xx | Server error | `search_error="tavily_error:502"`, pipeline lanjut |
| Edge — klaim dengan angka spesifik | "$0.03/1K tokens" → Tavily dapat "$0.015/1K tokens" | Scorer yang putuskan contradicted — verifier hanya pass data mentah |

---

## Phase 4 — Freshness Scorer

**File:** `src/freshness_scorer.py`

### Tanggung Jawab
Bandingkan klaim vs bukti Tavily → assign status per klaim.

### Status

| Status | Arti |
|--------|------|
| `confirmed_current` | Sumber terkini mendukung klaim |
| `contradicted` | Sumber terkini memuat fakta berbeda yang bertentangan |
| `unverifiable` | Tidak ada sumber relevan yang cukup untuk verdict |

### Scoring Strategy: LLM-as-Judge via Bifrost

```python
SCORE_PROMPT = """
Given this claim and web search results, determine if the claim is currently accurate.

Claim: {claim}
Category: {category}

Search Results:
{search_results}

Rules:
- confirmed_current: results clearly support the claim as still accurate
- contradicted: results contain specific contradicting evidence (different price, version, date, etc.)
- unverifiable: results are irrelevant, too old, or insufficient to make a verdict
- When uncertain, choose unverifiable — do not force a verdict

Return JSON only:
{
  "status": "confirmed_current|contradicted|unverifiable",
  "reasoning": "one sentence explanation",
  "contradicting_evidence": "exact quote from results (only if contradicted, else null)",
  "source_url": "URL of primary evidence (null if unverifiable)"
}
"""
```

### Output Type

```python
@dataclass
class ScoredClaim:
    claim: Claim
    status: Literal["confirmed_current", "contradicted", "unverifiable"]
    reasoning: str
    contradicting_evidence: str | None
    source_url: str | None
    source_date: str | None
```

### Cases

| Case | Setup | Expected Status |
|------|-------|-----------------|
| Positive — match | Klaim "Python 3.12", Tavily confirm "Python 3.12 current stable" | `confirmed_current` |
| Negative — mismatch | Klaim "$0.03/1K tokens", Tavily return "$0.015/1K tokens" | `contradicted` + source URL |
| Negative — outdated | Klaim "CEO: Elon Musk at Tesla", Tavily return "Elon Musk departed" | `contradicted` |
| Edge — no results | `results=[]` | `unverifiable` |
| Edge — results irrelevant | Tavily return off-topic pages | `unverifiable` |
| Edge — results too old | Tavily return 2019 article | `unverifiable` — tanggal publish di bawah threshold (>2 tahun) |
| Edge — scorer LLM invalid JSON | Bifrost return malformed response | Fallback ke `unverifiable`, log error |
| Edge — klaim subjektif lolos extractor | "Claude is best" masuk scorer | Scorer harus return `unverifiable` (tidak bisa diverifikasi secara objektif) |

---

## Phase 5 — Pipeline Orchestrator

**File:** `src/pipeline.py`

### Flow

```
llm_answer
    ↓
extract_claims()          → List[Claim]
    ↓
[verify_claim(c) for c]   → List[VerifiedClaim]   (concurrent, rate-limited)
    ↓
[score_claim(v) for v]    → List[ScoredClaim]      (concurrent)
    ↓
build_result()            → FreshnessReport
```

### Output Type

```python
@dataclass
class FreshnessReport:
    original_answer: str
    claims: list[ScoredClaim]
    summary: dict           # total, confirmed, contradicted, unverifiable counts
    mode: str               # "demo" | "production"
    duration_ms: int
```

### Concurrency

```python
import asyncio

async def run_pipeline(llm_answer: str) -> FreshnessReport:
    claims = await extract_claims(llm_answer)
    verified = await asyncio.gather(*[verify_claim(c) for c in claims])
    scored = await asyncio.gather(*[score_claim(v) for v in verified])
    ...
```

### Cases

| Case | Scenario | Expected |
|------|----------|----------|
| Positive | 3 klaim, semua terverifikasi | Report dengan 3 scored claims |
| Negative | 0 klaim diekstrak | `claims=[]`, summary semua 0 |
| Edge — partial failure | 1 dari 3 Tavily calls timeout | 2 scored normal, 1 `unverifiable` dengan `search_error` |
| Edge — Bifrost down | LLM call gagal di extractor | Raise `PipelineError` dengan pesan jelas |
| Edge — answer sangat panjang | >4000 kata | Truncate ke 3000 kata, tambahkan note di report |
| Edge — answer berisi klaim duplikat | "GPT-4 costs $0.03" disebut 2x | Deduplicate sebelum verify |

---

## Phase 6 — Demo Mode vs Production Mode

### Demo Mode (`APP_MODE=demo`)

Gunakan fixture pre-baked, tidak hit API eksternal. Cocok untuk presentasi offline / CI.

**File:** `demo/fixtures.py`

```python
DEMO_FIXTURES = [
    {
        "id": "outdated_pricing",
        "label": "LLM Pricing (Outdated)",
        "llm_answer": "GPT-4 Turbo costs $0.01 per 1K input tokens and $0.03 per 1K output tokens.",
        "expected": {
            "claims": [{"status": "contradicted", "category": "price"}]
        }
    },
    {
        "id": "correct_version",
        "label": "Python Version (Current)",
        "llm_answer": "Python 3.12 is the latest stable release with significant performance improvements.",
        "expected": {
            "claims": [
                {"status": "confirmed_current", "category": "version"},
            ]
        }
    },
    {
        "id": "no_claims",
        "label": "Opinion Only (No Claims)",
        "llm_answer": "AI assistants are generally becoming more helpful and easier to use.",
        "expected": {"claims": []}
    },
    {
        "id": "mixed_claims",
        "label": "Mixed: Some Stale, Some Current",
        "llm_answer": "OpenAI was founded in 2015 and GPT-4 API costs $0.01/1K tokens.",
        "expected": {
            "claims": [
                {"status": "confirmed_current", "category": "date"},
                {"status": "contradicted", "category": "price"},
            ]
        }
    },
    {
        "id": "unverifiable",
        "label": "Internal Fact (Unverifiable)",
        "llm_answer": "Acme Corp has 47 engineers in their ML team.",
        "expected": {
            "claims": [{"status": "unverifiable", "category": "entity"}]
        }
    },
]
```

Demo mode mengembalikan fixture result tanpa memanggil Bifrost/Tavily.

### Production Mode (`APP_MODE=production`)

- Hit Bifrost API untuk extractor + scorer
- Hit Tavily API untuk verifier
- Rate limiting aktif
- Logging lengkap per request

### Mode Switch di Pipeline

```python
async def run_pipeline(llm_answer: str) -> FreshnessReport:
    if settings.app_mode == AppMode.DEMO:
        return get_demo_result(llm_answer)   # match fixture by content
    return await run_production_pipeline(llm_answer)
```

---

## Phase 7 — UI

**File:** `ui/app.py`

### Endpoints

```
GET  /                  → HTML form
POST /check             → JSON FreshnessReport
GET  /demo              → HTML demo mode selector (pilih dari fixtures)
GET  /health            → {"status": "ok", "mode": "demo|production"}
```

### UI Behaviour

**Input form:**
- Textarea untuk paste jawaban LLM
- Mode badge (DEMO / PRODUCTION)
- Submit button

**Result view:**
- Jawaban original dengan inline highlight per klaim:
  - 🟢 `confirmed_current` — green underline
  - 🔴 `contradicted` — red underline + tooltip sumber + URL
  - 🟡 `unverifiable` — yellow underline
- Summary bar: `X confirmed · Y contradicted · Z unverifiable`
- Per-claim detail expandable: reasoning, source URL, source date

**Demo mode:**
- Dropdown pilih fixture
- Auto-populate textarea
- Jalankan → lihat hasil pre-baked

---

## Phase 8 — Tests

### Test Structure

```
tests/
├── test_extractor.py    # unit: prompt → parsed claims
├── test_verifier.py     # unit: query build + mock Tavily response
├── test_scorer.py       # unit: mock LLM judge verdicts
├── test_pipeline.py     # integration: full flow dengan mock API
└── conftest.py          # fixtures, mock clients
```

### Key Test Cases per Module

**test_extractor.py**
```python
def test_extracts_price_claim()
def test_extracts_multiple_claims()
def test_returns_empty_for_opinion_only()
def test_returns_empty_for_vague_claim()
def test_handles_mixed_content()
def test_handles_empty_input()
def test_handles_non_english_input()
def test_handles_invalid_llm_json_response()
```

**test_verifier.py**
```python
def test_builds_correct_query_per_category()
def test_returns_results_on_success()
def test_handles_zero_results()
def test_handles_tavily_timeout()
def test_handles_tavily_5xx_error()
def test_rate_limiting_in_production_mode()
```

**test_scorer.py**
```python
def test_returns_confirmed_when_evidence_matches()
def test_returns_contradicted_when_evidence_conflicts()
def test_returns_unverifiable_when_no_results()
def test_returns_unverifiable_when_results_irrelevant()
def test_returns_unverifiable_for_old_sources()
def test_fallback_to_unverifiable_on_invalid_json()
```

**test_pipeline.py**
```python
def test_full_pipeline_happy_path()
def test_pipeline_with_no_claims()
def test_pipeline_partial_verifier_failure()
def test_pipeline_deduplicates_claims()
def test_pipeline_truncates_long_input()
def test_demo_mode_uses_fixtures()
def test_demo_mode_does_not_call_apis()
```

---

## Urutan Eksekusi

```
Phase 1  Setup (env, deps, Bifrost)         ~30 menit
Phase 2  Claim Extractor                    ~1–2 jam
Phase 3  Claim Verifier                     ~1 jam
Phase 4  Freshness Scorer                   ~1–2 jam
Phase 5  Pipeline Orchestrator              ~1 jam
Phase 6  Demo Mode + Fixtures               ~1 jam
Phase 7  UI                                 ~1–2 jam
Phase 8  Tests                              ~1–2 jam
```

Tiap phase bisa dieksekusi mandiri. Phase 6 (demo mode) bisa dijalankan paralel setelah Phase 5 selesai interface-nya terbentuk.
