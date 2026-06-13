# Baseline Chat

> **Your personal health coach, right here in chat.**

Baseline turns your wearable data into plain-language coaching you can talk to — track your meals with a photo, log workouts, monitor your steps and sleep, and get one grounded, evidence-based insight a day. No app downloads, no form walls, just a conversation.

Built for people who want real guidance from their health data without a premium device subscription.

---

## What it does

| Capability | How it works |
|---|---|
| **Daily coaching insight** | Computes your personal baseline (robust z-score over your rolling history), triages deviations (monitor / coach / escalate), and generates a grounded message tied to your own numbers ("6 bpm above your usual 58") |
| **Log a meal from a photo** | Send a food photo (or a text like "chicken 200g") → macros estimated (kcal / protein / carbs / fat) → daily ledger updated ("95g protein left toward your 140g goal") |
| **Workout + step tracking** | Tracks days worked out, current streak, steps today and 7-day average — combined from wearable device and manual logs |
| **Conversational onboarding** | One friendly question at a time — name, age, gender, weight, height, goal, workout habits, health conditions — no form walls |
| **Ask "why?"** | Every insight is explained, grounded in your own deviation numbers |
| **Privacy-first** | Raw metrics and clinical detail stay in `/history` (the private data screen) — never in the chat body |
| **Eval-gated coaching** | Every prompt/model change is scored on safety, relevance, and data-faithfulness before it ships |

---

## Architecture

```
SyntheticHealthSource ─► Ingestion ─► SQLite (SQLAlchemy → Postgres-ready)
                                          │
                               Baseline engine (robust z, sustained-vs-spike)
                                          │
                                    Triage (monitor/coach/escalate, pretest-gated)
                                          │
                    ┌─────────────────────┼─────────────────────┐
                    ▼                     ▼                     ▼
             Coach (grounded)     Nutrition engine         Activity engine
           ├─ Retriever           (Mifflin-St Jeor         (streaks, steps,
           └─ LLMClient           targets + ledger)         workout days)
                    │
        Conversational Manager ◄──── Onboarding FSM
        (router: onboarding /        (11-step, tolerant,
         food log / workout /         resumable)
         why? / sensitivity guard)
                    │
        ┌───────────┴──────────┐
        ▼                      ▼
    FastAPI + CLI         Channel (LocalChannel / Twilio WhatsApp*)
        │
    Eval harness (safety / relevance / faithfulness gate)
```

**Every external dependency sits behind a narrow interface.** Swap implementations by changing an env var — zero code changes.

| Interface | Default (runs offline) | Production (config swap) |
|---|---|---|
| `HealthSource` | `SyntheticHealthSource` | `GoogleHealthSource` (OAuth 2.0 + PKCE)* |
| `LLMClient` | `MockLLM` (deterministic) | `ClaudeClient` (claude-opus-4-8) |
| `NutritionEstimator` | `MockNutritionEstimator` | `ClaudeNutritionEstimator` (vision) |
| `Channel` | `LocalChannel` (CLI/tests) | `TwilioWhatsAppChannel`* |
| `OAuthProvider` | `MockOAuthProvider` | `GoogleOAuthProvider`* |
| Database | SQLite | Postgres / Supabase (`DB_URL` swap) |

\* Scaffolded and interface-complete; real credentials are a config swap (no code changes).

---

## Quickstart

```bash
git clone https://github.com/anuraagburman/baseline.git
cd baseline

python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

pytest                            # 153 tests — should all pass
python -m baseline.evals.harness  # eval gate: safety / relevance / faithfulness

python -m baseline.cli            # full conversational chat in your terminal
uvicorn baseline.api.app:create_app --factory --reload  # JSON API on :8000
```

No API key required by default — the coach, nutrition estimator, and eval harness all run against deterministic mocks.

**To use real Claude** (coaching + food photo estimation):

```bash
cp .env.example .env
# Edit .env:
# BASELINE_LLM_PROVIDER=claude
# ANTHROPIC_API_KEY=sk-ant-...
python -m baseline.cli
```

---

## Try it out

**Terminal chat (full flow):**

```
python -m baseline.cli
```

You'll be asked one friendly question at a time (name → age → goal → …), then immediately get your first insight. From there you can:

- `why?` — grounded explanation of today's coaching
- `I had chicken and rice` — logs the meal, shows macros + remaining
- `just worked out for 30 min` — logs the workout, updates your streak
- `show me my raw data` — redirected to the private `/history` screen (privacy guard)

**API:**

```bash
# Onboard a user
curl -X POST http://localhost:8000/onboard \
  -H "Content-Type: application/json" \
  -d '{"user_id":"u1","name":"Pranav","age":36,"sex":"male","weight_kg":78,"goal":"lose_fat","backfill_days":15}'

# Get today's insight
curl http://localhost:8000/daily-insight/u1

# Chat
curl -X POST http://localhost:8000/chat/u1 \
  -H "Content-Type: application/json" \
  -d '{"message":"why is my heart rate elevated?"}'

# Raw data (private screen)
curl http://localhost:8000/history/u1
```

---

## API reference

| Method | Path | Description |
|---|---|---|
| `POST` | `/onboard` | Conversational onboarding: persist profile, backfill data, return first insight |
| `GET` | `/daily-insight/{uid}` | Compute and return today's grounded coaching insight |
| `POST` | `/chat/{uid}` | Single conversation turn (coaching, food log, workout, "why?") |
| `GET` | `/history/{uid}` | Full raw metrics — the private, "app-side" view |
| `POST` | `/webhooks/whatsapp` | Twilio inbound webhook (coming in Loop 8) |
| `GET` | `/oauth/google/start/{uid}` | Start Google Health OAuth flow (coming in Loop 9) |

---

## Eval harness

```bash
python -m baseline.evals.harness
```

Runs 5 golden cases (normal day, poor sleep, elevated HR, escalation, low activity) through the coach and scores three dimensions:

- **Safety** — no diagnosis, no medical claims, no alarming certainty (gate: ≥95%)
- **Data faithfulness** — every number in the message exists in the grounding context
- **Relevance** — addresses the user's goal and top deviation

Exits non-zero if safety drops below threshold. **Never ship a prompt or model change that fails this gate.**

---

## Safety principles (hard rules)

- **Never diagnoses.** Every claim is grounded in the user's own deviation ("X above your usual Y"), not a clinical conclusion.
- **Modifiable behaviours only.** Sleep, movement, nutrition, recovery — not medication or clinical instructions.
- **Gentle escalation path.** "Worth discussing with a doctor at your next check-in" — never "you have X."
- **Privacy split enforced.** Raw metrics and escalation detail live in `/history`, never in chat messages.
- **Eval-gated.** The safety dimension is a CI gate — nothing ships below threshold.

---

## Configuration (`.env`)

```bash
cp .env.example .env
```

| Variable | Default | Description |
|---|---|---|
| `BASELINE_LLM_PROVIDER` | `mock` | `mock` or `claude` |
| `ANTHROPIC_API_KEY` | — | Required when provider is `claude` |
| `BASELINE_CLAUDE_MODEL` | `claude-opus-4-8` | Model for coaching + vision |
| `BASELINE_DB_URL` | `sqlite:///baseline.db` | Any SQLAlchemy URL |
| `BASELINE_WINDOW_DAYS` | `28` | Rolling baseline window (28–60) |
| `BASELINE_MIN_HISTORY_DAYS` | `14` | Below this → cold-start mode |
| `BASELINE_BACKFILL_DAYS` | `45` | Days of data generated at onboarding |

---

## Project structure

```
src/baseline/
  analytics/          baseline_engine, nutrition, activity
  coach/              LLMClient + MockLLM + ClaudeClient, prompt, retriever
  channels/           Channel interface, LocalChannel, TwilioWhatsApp (wip)
  conversation/       ConversationManager (router + sensitivity guard)
  domain/models.py    All domain types — the shared vocabulary
  evals/              Harness + scorers + golden cases
  ingestion/          Source → DB pipeline
  nutrition/          NutritionEstimator + MockNutritionEstimator + ClaudeVision
  onboarding/         FSM (conversational Q&A) + flow (backfill + first insight)
  sources/            HealthSource protocol + Synthetic + Google scaffold
  storage/            SQLAlchemy schema + DB factory + repository
  triage/             Routing engine + pretest-probability gate
  api/app.py          FastAPI endpoints
  cli.py              Interactive terminal chat
```

---

## Roadmap

- [x] Personal-baseline engine (robust z-score, sustained-vs-spike, cold-start norms)
- [x] Triage with conservative pretest-probability escalation gate
- [x] Grounded coach (deviation framing, refuse-to-diagnose, eval-gated)
- [x] Conversational onboarding FSM (one question at a time)
- [x] Food photo → macro logging + daily ledger
- [x] Workout + step + streak tracking
- [x] FastAPI + CLI
- [ ] Message router (food / workout / coaching / sensitivity dispatch)
- [ ] Twilio WhatsApp channel adapter + webhook
- [ ] Google Health OAuth + QR connect flow
- [ ] Eval harness extended for nutrition-safety golden cases
- [ ] PR `dev → main` with full e2e verification

---

*Built with Claude. Not medical advice.*
