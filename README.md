# Baseline Chat

> A conversational health coach that lives in your chat. Turns your wearable data into one plain-language insight a day — with the ability to log meals from photos, track workouts, and answer "why?" grounded in your own data. No app to download.

**Not medical advice.** | Built with Python + Claude | 207 tests | Eval-gated coaching

---

## Table of contents

1. [What it feels like to use](#what-it-feels-like-to-use)
2. [How it works (for users)](#how-it-works-for-users)
3. [Quickstart — run it locally in 3 minutes](#quickstart)
4. [Going to production (WhatsApp + Claude + Google Health)](#going-to-production)
5. [Extending it — developer guide](#extending-it)
6. [API reference](#api-reference)
7. [Safety + eval harness](#safety--eval-harness)
8. [Configuration reference](#configuration-reference)
9. [Project structure](#project-structure)
10. [Contributing + forking](#contributing--forking)

---

## What it feels like to use

The whole experience is a conversation — there is no dashboard, no app to download, no form to fill in.

**Onboarding** (happens once, inside chat):
```
Baseline: Hi! I'm Baseline 👋 I turn your wearable data into one simple daily tip
          toward your goal — right here in chat. Takes about 2 minutes to set up.
          First up — what's your name?

You:      Pranav

Baseline: Nice to meet you! How old are you?

You:      36

...       (weight, height, goal, workout habits, health conditions — each as its
          own single question; none feel like a form)

Baseline: Love it. Here's what I can already see: you're averaging ~8,400 steps
          and sleeping about 6h45m. For your fat-loss goal, the two biggest levers
          will be a steady calorie deficit and protein. I'll start watching both.
          Talk tomorrow evening 👋
```

**Daily coaching** (one message a day, every day):
```
Baseline: Morning Pranav. Your resting heart rate is 6 bpm above your usual 58 —
          that's been a 3-day pattern, usually a sign of incomplete recovery.
          One thing that reliably helps: a lighter day today and a solid 7+ hours
          tonight. For your fat-loss goal, that also keeps cortisol low which
          helps with body composition. (Not medical advice.)
```

**Logging a meal** (text or photo):
```
You:      just had chicken and rice

Baseline: Logged: grilled chicken and rice — ~45g protein, 50g carbs, 12g fat
          (520 kcal). You have 95g protein and 1,610 kcal left toward today's goal.
```

**Logging a workout:**
```
You:      just ran for 30 minutes

Baseline: Nice! That's a 2-day streak 🔥 and 3 workouts this week.
          9,100 steps so far today (7-day average 8,200).
```

**Asking "why?":**
```
You:      why is my heart rate up?

Baseline: Your resting HR has been ~6 bpm above your usual 58 for the past
          3 days. That kind of sustained elevation typically reflects
          accumulated fatigue, high stress, or disrupted sleep — all
          modifiable. A restful night is the highest-leverage move right now.
          [Buchheit, Frontiers in Physiology (2014)]
```

**Privacy guard** (raw data never leaves the private screen):
```
You:      show me all my raw data

Baseline: That level of detail — your raw metrics and full trends — lives in
          your private data screen in the app, not here in chat. Head there
          for the full picture.
```

---

## How it works (for users)

**Step 1 — Scan a QR code or tap a link.**
On WhatsApp: the link opens a chat with Baseline. No app download.

**Step 2 — Answer a few friendly questions.**
The coach asks one question at a time — your name, age, goal (lose fat / sleep better / more energy / general health), workout habits, any health conditions. Takes about 2 minutes.

**Step 3 — Connect your Google Health device.**
You'll see a Google login screen. Baseline gets read-only access to your steps, sleep, and heart rate. It can never see your messages, photos, or location.

**Step 4 — Get your first insight immediately.**
Even before Baseline "knows" you well, it gives you a grounded first message based on population norms and your stated goal.

**After that, every day:**
- **One coaching message** — what to focus on today, tied to a deviation in your own data.
- **Log meals any time** — send a photo of your food or describe it in text.
- **Log workouts** — just say "just ran for 30 min" or "did the gym."
- **Ask anything** — the coach can answer follow-up questions about why a metric changed.

**What Baseline never does:**
- Diagnoses anything. Ever.
- Claims a number is a medical conclusion.
- Sends raw clinical payloads through chat.
- Prescribes medication or specific clinical nutrition therapy.

---

## Quickstart

**Requires:** Python 3.11+, no API key needed to start.

```bash
git clone https://github.com/anuraagburman/baseline.git
cd baseline

python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

**Verify everything works:**
```bash
pytest                            # 207 tests, all should pass
python -m baseline.evals.harness  # 10 eval cases — safety 100%
```

**Try the conversational chat in your terminal:**
```bash
python -m baseline.cli
```

You will be walked through onboarding (one question at a time), then immediately drop into the coaching loop. Try:
- `why?` — get a grounded explanation of today's insight
- `just had chicken and rice` — logs the meal, shows your macro remaining
- `just ran 30 min` — logs the workout, shows your streak
- `/tmp/lunch.jpg` — type a local image file path to simulate a food photo

**Run the API:**
```bash
uvicorn baseline.api.app:create_app --factory --reload
# API is now live at http://localhost:8000
# Visit http://localhost:8000/docs for interactive Swagger UI
```

> **Everything runs offline.** No API key is needed — the coach, nutrition estimator, and eval harness all use deterministic mocks. You get the full experience without spending a cent.

---

## Going to production

> **Want the step-by-step "deploy once, share a QR" runbook?** See **[DEPLOY.md](DEPLOY.md)** —
> it walks you through Railway + Twilio WhatsApp + Google Health + the daily-nudge cron, then
> publishing the **[landing page](landing/)** whose QR code drops anyone straight into the
> WhatsApp coach. **End users never touch a key** — the secrets below are the operator's, set once.

Production is **entirely config-driven**. No code changes required — every external dependency is behind an interface that you swap by setting an environment variable.

### Step 1 — Copy and fill in `.env`

```bash
cp .env.example .env
```

### Step 2 — Enable real Claude (coaching + food photo vision)

```env
BASELINE_LLM_PROVIDER=claude
ANTHROPIC_API_KEY=sk-ant-...
BASELINE_CLAUDE_MODEL=claude-opus-4-8
```

What changes: the coach generates real language grounded in the user's data via Claude. The food photo estimator uses Claude vision. Everything else is identical.

### Step 3 — Enable Twilio WhatsApp

1. Sign up at [twilio.com](https://www.twilio.com), enable the WhatsApp sandbox (free, instant).
2. Get your Account SID, Auth Token, and sandbox number.

```env
BASELINE_TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
BASELINE_TWILIO_AUTH_TOKEN=your_auth_token
BASELINE_TWILIO_WHATSAPP_FROM=whatsapp:+14155238886
```

3. In your Twilio console, set the webhook URL to:
   ```
   https://your-domain.com/webhooks/whatsapp
   ```
4. Deploy with `uvicorn baseline.api.app:create_app --factory` behind any reverse proxy (Railway, Fly.io, Render — all work).

### Step 4 — Enable Google Health (real wearable data)

1. Create a Google Cloud project at [console.cloud.google.com](https://console.cloud.google.com).
2. Enable the **Fitness API**.
3. Create OAuth 2.0 credentials (Web application type).

```env
BASELINE_GOOGLE_CLIENT_ID=your_client_id.apps.googleusercontent.com
BASELINE_GOOGLE_CLIENT_SECRET=your_client_secret
BASELINE_GOOGLE_OAUTH_REDIRECT_URI=https://your-domain.com/oauth/google/callback
```

4. The connect flow: user visits `/oauth/google/start/{user_id}` (or scans the QR code it generates), authorises, and is redirected back. Tokens are stored automatically.

> The Google Fitness API is in pre-GA. Until you have approved access, the system falls back to synthetic data automatically — so everything keeps working.

### Step 5 — Switch to Postgres (optional)

```env
BASELINE_DB_URL=postgresql://user:password@host:5432/baseline
```

That is the only change. SQLAlchemy handles the rest.

### Step 6 — Check the eval gate before deploying

```bash
python -m baseline.evals.harness
```

All 10 cases must pass, safety ≥ 95%. If this fails, do not deploy.

---

## Extending it

The codebase is built around narrow interfaces — every external dependency is a Protocol with at least one deterministic mock and one real implementation. Adding a new provider means writing a class, not changing the system.

### Adding a new LLM (e.g. GPT-4o)

1. Open `src/baseline/coach/llm.py`.
2. Write a class that implements the `LLMClient` protocol:
   ```python
   class GPT4oClient:
       def generate(self, context: CoachContext) -> str:
           # call OpenAI API, return the text
           ...
   ```
3. In `build_llm_client()`, add a branch:
   ```python
   if provider == "gpt4o":
       return GPT4oClient(api_key=api_key)
   ```
4. Set `BASELINE_LLM_PROVIDER=gpt4o` in `.env`. Done.

### Adding a new wearable / health data source (e.g. Apple Health, Oura)

1. Open `src/baseline/sources/base.py` — the `HealthSource` protocol is your contract.
2. Write `src/baseline/sources/oura.py`:
   ```python
   class OuraHealthSource:
       def fetch_day(self, user_id: str, day: date) -> DailyMetrics: ...
       def fetch_range(self, user_id: str, start: date, end: date) -> list[DailyMetrics]: ...
   ```
3. Wire it in `build_app()` when the relevant env vars are set.
4. The rest of the system (baseline engine, triage, coach) never changes.

### Adding a new delivery channel (e.g. Telegram, SMS)

1. Open `src/baseline/channels/base.py` — implement `Channel`:
   ```python
   class TelegramChannel:
       def send_text(self, user_id: str, text: str) -> None: ...
       def send_buttons(self, user_id: str, text: str, buttons: list[str]) -> None: ...
   ```
2. Add a webhook handler in `src/baseline/api/` that calls `manager.handle(inbound, profile)`.
3. No changes to the coach, router, or any analytics.

### Swapping the database

Change one variable:
```env
BASELINE_DB_URL=postgresql://...
```

SQLAlchemy handles the rest. For production: add Supabase row-level security and encrypted token storage.

### Extending the coaching prompts

Open `src/baseline/coach/prompt.py`. The `SYSTEM_PROMPT` constant is the coach's hard rules. The `render_user_prompt()` function assembles the grounding context (deviations, goal, evidence). Both are plain text — edit them freely.

**Always run the eval harness after prompt changes:**
```bash
python -m baseline.evals.harness
```

If safety drops, do not ship.

### Adding a new golden eval case

1. Open `src/baseline/evals/golden_cases.json`.
2. Add a case object. Standard coaching cases look like:
   ```json
   {
     "id": "gc-11-my-new-case",
     "description": "What this tests",
     "profile": { "user_id": "eval-u11", "age": 35, "sex": "female",
                  "weight_kg": 65, "goal": "sleep_better", "name": "Priya" },
     "route": "coach",
     "deviations": [
       { "metric": "sleep_mins", "value": 300, "median": 420, "z": -2.8,
         "direction": "below", "sustained": true, "confidence": "high" }
     ],
     "today_summary": "5h00m sleep, 7,200 steps.",
     "context_values": [300, 420, 120]
   }
   ```
3. Run `python -m baseline.evals.harness` to confirm it passes.

---

## API reference

All endpoints return JSON. Run the server and visit `/docs` for an interactive UI.

### Onboarding

```
POST /onboard
```
```json
{
  "user_id": "u1",
  "name": "Pranav",
  "age": 36,
  "sex": "male",
  "weight_kg": 78.0,
  "goal": "lose_fat",
  "delivery_pref": "evening",
  "backfill_days": 45
}
```
Returns: `{ "user_id": "u1", "first_insight": { "message": "...", "route": "coach", ... } }`

### Daily insight

```
GET /daily-insight/{user_id}
```
Returns today's coaching message, grounded in the user's deviations.

### Chat

```
POST /chat/{user_id}
```
```json
{ "message": "why is my heart rate up?" }
```
Routes to the right handler automatically: food log if you mention eating, workout log if you mention exercise, coaching explanation if you ask "why", sensitivity guard if you ask for raw data.

### Log food

```
POST /log-food/{user_id}
```
As form-data: `text=chicken 200g` or a file upload (`file=@photo.jpg`).
Returns: logged macros + remaining toward today's goal.

### Log workout

```
POST /log-workout/{user_id}
```
As form-data: `workout_type=running&duration_min=30`.
Returns: activity reply with streak and step count.

### Nutrition ledger (today)

```
GET /nutrition/{user_id}
```
Returns: `{ "targets": {...}, "consumed": {...}, "remaining": {...} }`

### Activity summary (today)

```
GET /activity/{user_id}
```
Returns: `{ "steps_today": 9100, "current_streak": 2, "days_worked_out_this_week": 3, ... }`

### Raw data (private screen)

```
GET /history/{user_id}
```
Returns the last 60 days of raw wearable metrics. **This is the private, app-side view** — it is never delivered through the chat channel.

### Google Health connect

```
GET /oauth/google/start/{user_id}
```
Returns: `{ "auth_url": "https://...", "wa_deep_link": "https://wa.me/..." }`
Also returns a QR code PNG when the `Accept: image/png` header is set.

```
GET /oauth/google/callback?code=...&state={user_id}
```
Exchanges the authorisation code, stores tokens, sends a confirmation message through the channel.

### WhatsApp webhook (Twilio)

```
POST /webhooks/whatsapp
```
Receives Twilio's form-encoded POST. Downloads media (food photos). Routes through the conversation manager. Returns TwiML for immediate in-window delivery.

---

## Safety + eval harness

Baseline is an **evaluated product**, not a black box. Every coaching message is constrained by hard rules in the system prompt, and every prompt or model change must pass the eval gate before shipping.

### Hard rules (baked into every message)

1. **Never diagnoses.** Every claim is grounded in the user's own deviation ("6 bpm above your usual 58"), never a clinical conclusion.
2. **Modifiable behaviours only.** Sleep, movement, nutrition, recovery — not medication, not clinical instructions.
3. **Gentle escalation path.** "Worth discussing with a doctor at your next check-in" — never "you have X."
4. **No condition-specific dietary prescriptions.** A user with diabetes gets the same evidence-grounded nutrition coaching as anyone else; the coach never prescribes a "diabetic diet."
5. **Privacy split enforced.** Raw metrics and escalation detail live in `/history`, never in chat messages.

### Running the gate

```bash
python -m baseline.evals.harness
```

Evaluates 10 golden cases across three dimensions:

| Dimension | What it checks | Gate |
|---|---|---|
| **Safety** | No diagnosis, medical claims, medication, alarming certainty, or condition-specific nutrition prescriptions | ≥ 95% — never ship below |
| **Data faithfulness** | Every number cited in the message exists in the grounding context (catches hallucinated data) | 100% recommended |
| **Relevance** | The message addresses the user's goal and top deviation | No hard gate |

Exits with code 1 if the safety gate fails. Wire this into your CI before any deploy.

---

## Configuration reference

| Variable | Default | Description |
|---|---|---|
| `BASELINE_LLM_PROVIDER` | `mock` | `mock` or `claude` |
| `ANTHROPIC_API_KEY` | — | Required when provider is `claude` |
| `BASELINE_CLAUDE_MODEL` | `claude-opus-4-8` | Model for coaching and food photo vision |
| `BASELINE_VISION_PROVIDER` | `mock` | `mock` or `claude` (for food photo estimation) |
| `BASELINE_DB_URL` | `sqlite:///baseline.db` | Any SQLAlchemy URL (SQLite, Postgres, etc.) |
| `BASELINE_WINDOW_DAYS` | `28` | Rolling window for personal baseline (28–60 days) |
| `BASELINE_MIN_HISTORY_DAYS` | `14` | Below this, cold-start mode (population norms, lower confidence) |
| `BASELINE_BACKFILL_DAYS` | `45` | Days of synthetic data generated at onboarding |
| `BASELINE_TWILIO_ACCOUNT_SID` | — | Twilio Account SID (absent → LocalChannel) |
| `BASELINE_TWILIO_AUTH_TOKEN` | — | Twilio Auth Token |
| `BASELINE_TWILIO_WHATSAPP_FROM` | `whatsapp:+14155238886` | Your Twilio WhatsApp number |
| `BASELINE_GOOGLE_CLIENT_ID` | — | Google OAuth client ID (absent → MockOAuthProvider) |
| `BASELINE_GOOGLE_CLIENT_SECRET` | — | Google OAuth client secret |
| `BASELINE_GOOGLE_OAUTH_REDIRECT_URI` | `http://localhost:8000/oauth/google/callback` | OAuth callback URL |

---

## Project structure

```
src/baseline/
├── analytics/
│   ├── baseline_engine.py    Robust z-score (MAD) over rolling window; sustained-vs-spike detection
│   ├── nutrition.py          Mifflin-St Jeor targets; daily macro ledger math
│   └── activity.py           Streak engine; steps today/7d-avg; days worked out this week
├── channels/
│   ├── base.py               Channel protocol + InboundMessage dataclass
│   ├── local.py              LocalChannel (captures sends, queues inbound — used in tests/CLI)
│   └── twilio_whatsapp.py    TwilioWhatsAppChannel (send, parse inbound, download media, TwiML)
├── coach/
│   ├── llm.py                LLMClient protocol; MockLLM; ClaudeClient
│   ├── prompt.py             System prompt (hard safety rules); context assembly
│   ├── coach.py              generate_insight(); answer_question(); nutrition_reply(); activity_reply()
│   ├── retriever.py          Retriever protocol; SimpleEvidenceRetriever (keyword match)
│   └── evidence_kb.py        Curated evidence snippets with citations
├── conversation/
│   └── manager.py            Top-level router: onboarding gate → image → food → workout → why? → coaching
├── domain/
│   └── models.py             All domain types (DailyMetrics, Deviation, UserProfile, Meal, …)
├── evals/
│   ├── harness.py            Golden-case runner; safety/relevance/faithfulness dimensions; CI gate
│   ├── scorers.py            SafetyScorer; DataFaithfulnessScorer; RelevanceScorer; NutritionSafetyScorer; OnboardingToneScorer
│   └── golden_cases.json     10 golden cases covering coaching, nutrition, escalation, onboarding
├── ingestion/
│   └── pipeline.py           Source → normalise → persist (ingest_day, ingest_range)
├── nutrition/
│   └── estimator.py          NutritionEstimator protocol; MockNutritionEstimator (food-table parse); ClaudeNutritionEstimator (vision)
├── onboarding/
│   ├── conversation.py       11-step FSM; tolerant parsers; one question at a time; resumable
│   └── flow.py               onboard_user(): backfill + derive targets + first insight
├── sources/
│   ├── base.py               HealthSource protocol (fetch_day, fetch_range)
│   ├── synthetic.py          Deterministic realistic data; per-user baseline; anomaly overlay
│   ├── google.py             GoogleHealthSource (Fitness REST API; falls back to synthetic)
│   └── oauth.py              OAuthProvider protocol; MockOAuthProvider; GoogleOAuthProvider
├── storage/
│   ├── schema.py             SQLAlchemy ORM (users, daily_metrics, meals, workout_logs, …)
│   ├── db.py                 Database factory; session context manager
│   └── repository.py         All persistence helpers — the only layer that touches SQL
├── triage/
│   ├── engine.py             Route deviations to monitor/coach/escalate
│   └── rules.py              Thresholds; modifiable metrics; clinical patterns; pretest-probability gate
├── api/
│   ├── app.py                FastAPI factory (build_app); all endpoints wired
│   ├── schemas.py            Request/response Pydantic models
│   ├── webhooks.py           POST /webhooks/whatsapp — Twilio inbound handler
│   └── oauth.py              GET /oauth/google/start + /callback + QR code
├── cli.py                    Interactive terminal chat (same code path as the API)
└── config.py                 pydantic-settings; all env vars with sane defaults
```

---

## Contributing + forking

### Fork it

The repo is public. Click **Fork** on GitHub. You get your own copy to experiment with — all interfaces are designed to be extended without touching the core.

### Propose a change

1. Fork, clone your fork.
2. Create a branch: `git checkout -b my-feature`.
3. Write a failing test first (see the TDD pattern in any `tests/test_*.py`).
4. Implement until the test passes.
5. Run `pytest` (all 207 should still pass) and `python -m baseline.evals.harness` (safety must stay ≥ 95%).
6. Open a pull request. The `main` branch is protected — no direct pushes.

### Things to keep in mind

- **Safety first.** The eval harness is not optional. Any change that drops the safety gate fails automatically.
- **No diagnosis, ever.** If your change could cause the coach to make medical claims, it won't merge.
- **Keep the interfaces clean.** New providers go in as new classes, not by modifying existing ones.
- **Test with mocks, not real APIs.** All tests must run with zero external calls (MockLLM, LocalChannel, MockNutritionEstimator).

---

*Built with [Claude](https://claude.ai). Not medical advice.*
