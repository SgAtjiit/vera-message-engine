# vera-bot ⚡

> **Intelligent WhatsApp Merchant Assistant for magicpin**  
> Stateful, grounded, multi-turn AI assistant built with FastAPI, 4-context state engine, and composite priority scoring.

---

## Overview

`vera-bot` empowers local merchants (salons, gyms, restaurants, pharmacies, dental clinics) on WhatsApp with timely, hyper-relevant notifications and multi-turn conversational reply handling.

### Key Capabilities
- **4-Context Engine**: In-memory, thread-safe ingestion and caching of `Category`, `Merchant`, `Customer`, and `Trigger` contexts.
- **Decision Quality & Grounding**: Composite trigger prioritization (tier weights + urgency + live signals) with strict literal grounding (zero hallucinated numbers/claims).
- **Conversational Replies**: Intent classification across `send`, `wait`, and `end` with automated WhatsApp drafting and varied, frictionless CTAs.
- **Sub-Millisecond Liveness**: Lightweight `/v1/healthz` endpoint with precomputed O(1) state counters.
- **Production Ready**: Containerized with Docker and ready for one-click deployment on Render.

---

## Architecture & Project Structure

```
├── app/
│   ├── main.py              # FastAPI application entrypoint & lifespan dataset loader
│   ├── config.py            # Service metadata (team, model, approach, version)
│   ├── models.py            # Pydantic v2 schemas for all API payloads
│   ├── state.py             # Thread-safe in-memory 4-context store & session histories
│   ├── composer.py          # Grounded message composer (3-part CTA formula)
│   └── endpoints/
│       ├── health.py        # GET /v1/healthz (lightweight O(1) liveness probe)
│       ├── metadata.py      # GET /v1/metadata (team & model metadata)
│       ├── context.py       # POST /v1/context (idempotent context ingestion)
│       ├── tick.py          # POST /v1/tick (simulation tick & trigger prioritization)
│       └── reply.py         # POST /v1/reply (multi-turn conversational reply engine)
├── dataset/                 # Seed data schemas and dataset generator
├── expanded/                # 355 expanded benchmark context documents
├── tests/                   # Pytest test suite (100% passing)
├── judge_simulator.py       # Offline evaluation harness & LLM judge
├── Dockerfile               # Production slim Dockerfile (dynamic $PORT support)
├── render.yaml              # Render blueprint specification
├── requirements.txt         # Core dependencies
└── .env.example             # Safe environment configuration template
```

---

## API Reference

All endpoints adhere strictly to the challenge specification and respond within strict execution deadlines (<25s guaranteed by timeout middleware).

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/v1/healthz` | Lightweight liveness check (uptime & context counts in O(1)) |
| `GET` | `/v1/metadata` | Service metadata, team name, and active approach |
| `POST` | `/v1/context` | Idempotent upsert of Category, Merchant, Customer, or Trigger |
| `POST` | `/v1/tick` | Evaluates triggers on simulation ticks; returns top priority actions |
| `POST` | `/v1/reply` | Multi-turn conversational reply handling (`send`, `wait`, `end`) |

---

## Getting Started

### 1. Local Setup

```bash
# Clone and enter directory
git clone <repo-url>
cd magicPin

# Create virtual environment
python -m venv .venv
source .venv/bin/activate    # Linux / macOS
# .venv\Scripts\activate     # Windows

# Install dependencies
pip install -r requirements.txt

# Configure environment (safe template)
cp .env.example .env
```

### 2. Run the Service

```bash
# Start server with Uvicorn (binds to port 8080)
uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
```

Verify the service is live:
```bash
curl http://localhost:8080/v1/healthz
```

---

## Security & Sensitive Data Protection

> [!NOTE]
> **Zero-Leak Policy**: All sensitive credentials, LLM API keys (`GROQ_API_KEY`, `OPENAI_API_KEY`), and environment secrets are kept exclusively in local `.env` files and are strictly prevented from ever being committed via `.gitignore` and `.dockerignore`.
>
> - Only the sanitized [`.env.example`](.env.example) template is tracked in version control.
> - Secrets on Render or production hosts should be provided through the deployment platform's encrypted environment variables dashboard.

---

## Deployment

### Deploy to Render (Free Tier)
1. Push this repository to GitHub.
2. In Render, select **New +** > **Blueprint**.
3. Connect your repository — Render automatically detects `render.yaml`.
4. In the Render Dashboard, add your `GROQ_API_KEY` (or alternative LLM key) under Environment Variables.
5. Deploy! Render will build the Docker container and monitor health via `/v1/healthz`.

### Docker (Local Build)
```bash
docker build -t vera-bot .
docker run -p 8080:8080 -e PORT=8080 -e GROQ_API_KEY="your_key" vera-bot
```

---

## Testing & Evaluation

### Run Test Suite
```bash
pytest
```

### Run Judge Simulator
```bash
# Run judge against the local server
python judge_simulator.py
```
