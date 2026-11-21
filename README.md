# FreshCheck

**Stale-claim detector for LLM answers.**

Paste any LLM-generated answer. FreshCheck extracts factual claims (prices, versions, dates, regulations, named entities), re-verifies each one against live web sources via Tavily, and returns a per-claim freshness verdict: `confirmed current`, `contradicted`, or `unverifiable` — with citations.

Built for the **Global AI Hackathon** (Geek Room) — Problem Statement #6: *Build a Stale-Answer Detector for AI Applications*.

---

## How It Works

```
LLM Answer
    ↓
Claim Extractor  — Bifrost (LLM routing, provider-agnostic)
    ↓
Claim Verifier   — Tavily Search API (live web)
    ↓
Freshness Scorer — Bifrost LLM-as-judge
    ↓
Annotated Output — per-claim: confirmed | contradicted | unverifiable
```

**Two modes:**
- `demo` — uses pre-baked fixtures, no API calls required. Good for local preview.
- `production` — hits Bifrost + Tavily APIs for real-time verification.

---

## Tech Stack

| Component | Technology |
|-----------|------------|
| LLM routing | [Bifrost](https://github.com/maximhq/bifrost) |
| Web search | [Tavily API](https://docs.tavily.com) |
| Backend | Python 3.11+, FastAPI, Uvicorn |
| Frontend | Jinja2 templates, Tailwind CSS |
| Testing | pytest, pytest-asyncio |

---

## Prerequisites

| Requirement | Version |
|-------------|---------|
| Python | 3.11+ |
| Bifrost | Running locally or cloud endpoint |
| Tavily API key | From [app.tavily.com](https://app.tavily.com) |

---

## Running on macOS

### 1. Clone & create virtual environment

```bash
git clone https://github.com/your-org/fresh-check.git
cd fresh-check
python3 -m venv .venv
source .venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment

```bash
cp .env.example .env
```

Edit `.env`:

```env
APP_MODE=demo           # demo or production

# Bifrost (required for production mode)
BIFROST_BASE_URL=http://localhost:8080
BIFROST_API_KEY=your_key_here
LLM_MODEL=gpt-4o-mini

# Tavily (required for production mode)
TAVILY_API_KEY=your_key_here
TAVILY_MAX_RESULTS=3
```

### 4. Start Bifrost (production mode only)

```bash
docker run -p 8080:8080 maximhq/bifrost
```

> Skip this step for demo mode.

### 5. Run the app

```bash
uvicorn ui.app:app --reload
```

Open [http://localhost:8000](http://localhost:8000)

---

## Running on Windows

### 1. Clone & create virtual environment

```powershell
git clone https://github.com/your-org/fresh-check.git
cd fresh-check
python -m venv .venv
.venv\Scripts\activate
```

### 2. Install dependencies

```powershell
pip install -r requirements.txt
```

### 3. Configure environment

```powershell
copy .env.example .env
```

Edit `.env` with Notepad or any editor:

```env
APP_MODE=demo

BIFROST_BASE_URL=http://localhost:8080
BIFROST_API_KEY=your_key_here
LLM_MODEL=gpt-4o-mini

TAVILY_API_KEY=your_key_here
TAVILY_MAX_RESULTS=3
```

### 4. Start Bifrost (production mode only)

```powershell
docker run -p 8080:8080 maximhq/bifrost
```

> Requires [Docker Desktop for Windows](https://docs.docker.com/desktop/windows/).

### 5. Run the app

```powershell
uvicorn ui.app:app --reload
```

Open [http://localhost:8000](http://localhost:8000)

> **Note:** If `uvicorn` is not found, use: `python -m uvicorn ui.app:app --reload`

---

## Running on a VPS (Ubuntu/Debian)

### 1. Install system dependencies

```bash
sudo apt update && sudo apt install -y python3.11 python3.11-venv python3-pip git
```

### 2. Clone & create virtual environment

```bash
git clone https://github.com/your-org/fresh-check.git
cd fresh-check
python3.11 -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment

```bash
cp .env.example .env
nano .env
```

```env
APP_MODE=production

BIFROST_BASE_URL=http://localhost:8080
BIFROST_API_KEY=your_key_here
LLM_MODEL=gpt-4o-mini

TAVILY_API_KEY=your_key_here
TAVILY_MAX_RESULTS=3
TAVILY_RATE_LIMIT_RPM=10
```

### 5. Start Bifrost

```bash
# Install Docker if not present
curl -fsSL https://get.docker.com | sh

docker run -d --name bifrost -p 8080:8080 maximhq/bifrost
```

### 6. Run the app (foreground, for testing)

```bash
uvicorn ui.app:app --host 0.0.0.0 --port 8000
```

### 7. Run as a background service (systemd)

Create `/etc/systemd/system/freshcheck.service`:

```ini
[Unit]
Description=FreshCheck
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/fresh-check
Environment="PATH=/home/ubuntu/fresh-check/.venv/bin"
ExecStart=/home/ubuntu/fresh-check/.venv/bin/uvicorn ui.app:app --host 0.0.0.0 --port 8000
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable freshcheck
sudo systemctl start freshcheck
sudo systemctl status freshcheck
```

### 8. Reverse proxy with Nginx (optional)

```bash
sudo apt install -y nginx
```

`/etc/nginx/sites-available/freshcheck`:

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/freshcheck /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

---

## Running Tests

```bash
# All tests
pytest

# With verbose output
pytest -v

# Specific module
pytest tests/test_extractor.py
pytest tests/test_verifier.py
pytest tests/test_scorer.py
pytest tests/test_pipeline.py
pytest tests/test_ui.py
```

Expected: **108 tests, 0 failures**

---

## Project Structure

```
fresh-check/
├── src/
│   ├── config.py              # Settings, AppMode enum
│   ├── models.py              # Claim, ScoredClaim, FreshnessReport, etc.
│   ├── exceptions.py          # Typed errors per layer
│   ├── claim_extractor.py     # Bifrost LLM call → List[Claim]
│   ├── claim_verifier.py      # Tavily search per claim → evidence
│   ├── freshness_scorer.py    # LLM-as-judge → status per claim
│   └── pipeline.py            # Async orchestrator
├── ui/
│   ├── app.py                 # FastAPI server
│   └── templates/
│       └── index.html         # UI: form, annotations, claim cards
├── demo/
│   └── fixtures.py            # Pre-baked demo fixtures
├── tests/
│   ├── conftest.py
│   ├── test_extractor.py
│   ├── test_verifier.py
│   ├── test_scorer.py
│   ├── test_pipeline.py
│   └── test_ui.py
├── .env.example
├── requirements.txt
├── pytest.ini
└── README.md
```

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Web UI |
| `POST` | `/check` | Check freshness of an LLM answer |
| `GET` | `/health` | Health check |

### POST /check

**Request:**
```json
{
  "llm_answer": "GPT-4 Turbo costs $0.01 per 1K input tokens."
}
```

**Response:**
```json
{
  "mode": "demo",
  "duration_ms": 42,
  "original_answer": "...",
  "annotated_answer": "<mark class=\"fc-contradicted\">...</mark>",
  "summary": {
    "total": 1,
    "confirmed": 0,
    "contradicted": 1,
    "unverifiable": 0
  },
  "claims": [
    {
      "claim": "GPT-4 Turbo costs $0.01 per 1K input tokens",
      "category": "price",
      "status": "contradicted",
      "reasoning": "OpenAI updated pricing in 2024.",
      "contradicting_evidence": "GPT-4 Turbo is now $0.005/1K tokens.",
      "source_url": "https://openai.com/pricing",
      "source_date": "2026-03-01"
    }
  ]
}
```

---

## Claim Categories

| Category | Examples |
|----------|---------|
| `price` | API costs, subscription fees, product pricing |
| `version` | Software versions, API versions, release numbers |
| `date` | Release dates, deadlines, event dates |
| `regulation` | Laws, compliance standards, policy names |
| `entity` | CEO names, company headcount, funding amounts |

---

## Verdict Reference

| Status | Meaning |
|--------|---------|
| `confirmed_current` | Live sources support the claim |
| `contradicted` | Live sources contradict the claim — includes citation |
| `unverifiable` | Insufficient or outdated sources to make a verdict |
