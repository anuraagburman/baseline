# Baseline Chat

A conversational, prevention-first AI health coach that turns your wearable data
into one plain-language, evidence-grounded insight a day — and lets you ask it
"why?" Built for people who *don't* have a premium device coach.

> **v1 status:** full coaching loop working end-to-end — synthetic data,
> personal-baseline engine, grounded coach, eval gate, FastAPI + CLI chat.
> Every heavy integration (Google Health, WhatsApp, real Claude, Postgres,
> pgvector RAG) sits behind a clean interface, ready to slot in without a rewrite.

## What it does

1. **Ingests** wearable metrics (v1: synthetic; later: Google Health OAuth)
2. **Computes your personal baseline** using a robust median + MAD z-score over a
   rolling window, flagging sustained trends vs. one-off spikes
3. **Triages** deviations — monitor / coach / escalate — with a conservative
   pretest-probability gate that prevents false-alarming low-risk users
4. **Generates a grounded coaching message** tied to your own deviation numbers
   ("6 bpm above your usual 58"), your stated goal, and curated evidence
5. **Lets you have a conversation** — ask "why?", ask follow-up questions — with
   a sensitivity guard that keeps raw clinical data out of the chat
6. **Gates every prompt/model change** through a safety / relevance /
   data-faithfulness eval harness before it reaches users

## Architecture

```
SyntheticHealthSource ─► Ingestion ─► SQLite (SQLAlchemy)
                                         │
                              Baseline engine (robust z, EWMA, sustained-vs-spike)
                                         │
                                   Triage (monitor/coach/escalate, pretest-gated)
                                         │
                              Coach (grounded prompt) ─┬─ Retriever (curated evidence)
                                         │             └─ LLMClient (MockLLM | Claude)
                                         │
                          Conversation manager ─► FastAPI / CLI
                                         │
                                Eval harness (safety / relevance / faithfulness)
```

**Every external dependency is behind a narrow interface:**

| Interface | v1 implementation | Production (ready to wire) |
|---|---|---|
| `HealthSource` | `SyntheticHealthSource` | `GoogleHealthSource` (OAuth 2.0 + PKCE) |
| `LLMClient` | `MockLLM` (deterministic) | `ClaudeClient` (claude-opus-4-8) |
| `Retriever` | `SimpleEvidenceRetriever` | `VectorRetriever` (pgvector) |
| DB | SQLite | Postgres / Supabase (`DB_URL` swap) |
| Channel | FastAPI + CLI | WhatsApp BSP adapter |

## Quickstart

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

pytest                           # 93 tests — should all pass
python -m baseline.evals.harness # eval gate: safety / relevance / faithfulness

python -m baseline.cli           # terminal chat (no API key needed)
uvicorn baseline.api.app:create_app --factory --reload  # JSON API on :8000
```

No API key needed by default — the coach runs against a deterministic mock LLM.

**To use real Claude:**

```bash
cp .env.example .env
# Edit .env: BASELINE_LLM_PROVIDER=claude, ANTHROPIC_API_KEY=sk-ant-...
python -m baseline.cli
```

## API endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/onboard` | Profile + backfill + first insight |
| `GET` | `/daily-insight/{uid}` | Today's coaching insight |
| `POST` | `/chat/{uid}` | Conversation turn |
| `GET` | `/history/{uid}` | Raw metrics (the private "app-side" view) |

## Safety

Baseline never diagnoses. Hard rules baked into the system prompt and verified
by the eval harness on every change:
- Claim anything? Ground it in the user's **own** deviation numbers.
- Suggest an action? It must be **modifiable behaviour** (sleep, movement, etc.).
- Genuinely worrying pattern? "Worth discussing with a doctor" — never a conclusion.
- Sensitive raw data stays in `/history`, never in the chat body.

## Eval harness

```
python -m baseline.evals.harness
```

Scores 5 golden cases on three dimensions. Exits non-zero if the safety pass
rate drops below 95% — the never-ship-below gate from the PRD.

## What comes next (interfaces already in place)

- `GoogleHealthSource` — real OAuth 2.0 + PKCE wearable ingestion
- `ClaudeClient` — real Anthropic API coaching (`BASELINE_LLM_PROVIDER=claude`)
- `VectorRetriever` — pgvector RAG over day-summary + evidence embeddings
- WhatsApp BSP channel adapter (inbound-first, utility templates)
- Postgres / Supabase with row-level security (`BASELINE_DB_URL` swap)
- Eval harness wired into CI as a release gate
