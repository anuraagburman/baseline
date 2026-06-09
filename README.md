# Baseline Chat

A conversational, prevention-first AI health coach that turns your wearable data
into one plain-language, evidence-grounded decision a day — and lets you ask it
"why?". Built for people who *don't* have a premium device coach.

> **v1 status:** core coaching loop, end-to-end, on synthetic data. Heavy
> external integrations (Google Health, WhatsApp, pgvector RAG, real Claude,
> Postgres) sit behind clean interfaces and slot in without a rewrite. See
> `docs`/the implementation plan for the full roadmap.

## Design at a glance

```
SyntheticHealthSource ─► Ingestion ─► SQLite (SQLAlchemy)
                                         │
                              Baseline engine (robust z, EWMA)
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

Every external dependency lives behind a narrow interface. v1 ships the simplest
real implementation of each.

## Quickstart

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest                                   # full test suite
python -m baseline.evals.harness         # run the coaching eval gate
python -m baseline.cli                   # chat with the coach in your terminal
uvicorn baseline.api.app:app --reload    # JSON API on :8000
```

No API key is needed: the coach runs against a deterministic mock LLM by
default. To use real Claude, set `BASELINE_LLM_PROVIDER=claude` and
`ANTHROPIC_API_KEY` (see `.env.example`).

## Safety

Baseline never diagnoses. Every claim is tied to the user's own data and framed
as a deviation from their personal normal; sensitive raw data stays out of the
chat body. The eval harness gates coach output on a safety dimension that must
never regress.
