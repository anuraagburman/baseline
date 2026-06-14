"""End-to-end test — drives the complete user journey with zero external calls.

Runs: onboarding → food log → workout → daily insight → why? → sensitivity
guard → eval harness gate → OAuth scaffold. All with LocalChannel, MockLLM,
MockNutritionEstimator, MockOAuthProvider.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from baseline.api.app import build_app
from baseline.evals.harness import run_harness


@pytest.fixture
def app(tmp_path):
    return build_app(
        db_url=f"sqlite:///{tmp_path}/e2e.db",
        llm_provider="mock",
        vision_provider="mock",
    )


@pytest.fixture
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


pytestmark = pytest.mark.anyio


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


# ---- Step 1: Onboard ----

async def test_e2e_01_onboard_returns_first_insight(client):
    resp = await client.post("/onboard", json={
        "user_id": "e2e_user", "name": "Pranav", "age": 36,
        "sex": "male", "weight_kg": 78.0, "goal": "lose_fat",
        "delivery_pref": "evening", "backfill_days": 20,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["user_id"] == "e2e_user"
    assert data["first_insight"]["message"]
    assert data["first_insight"]["route"] in {"monitor", "coach", "escalate"}


# ---- Step 2: Food log ----

async def test_e2e_02_food_log_text_returns_ledger(client):
    await _onboard(client)
    resp = await client.post("/log-food/e2e_user", data={"text": "chicken 200g and rice"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["meal"]["source"] == "text"
    assert "protein_g" in data["ledger_remaining"]
    assert "logged" in data["reply"].lower() or "protein" in data["reply"].lower()


async def test_e2e_02b_nutrition_ledger_reflects_logged_meal(client):
    await _onboard(client)
    await client.post("/log-food/e2e_user", data={"text": "chicken 150g"})
    resp = await client.get("/nutrition/e2e_user")
    assert resp.status_code == 200
    data = resp.json()
    assert data["consumed"]["protein_g"] > 0


# ---- Step 3: Workout log ----

async def test_e2e_03_workout_log_returns_activity_reply(client):
    await _onboard(client)
    resp = await client.post(
        "/log-workout/e2e_user",
        data={"workout_type": "running", "duration_min": "30"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "reply" in data
    assert data["activity"]["days_worked_out_this_week"] >= 1


async def test_e2e_03b_activity_streak_increments(client):
    await _onboard(client)
    await client.post("/log-workout/e2e_user", data={"workout_type": "yoga", "duration_min": "20"})
    resp = await client.get("/activity/e2e_user")
    assert resp.status_code == 200
    assert resp.json()["days_worked_out_this_week"] >= 1


# ---- Step 4: Daily insight ----

async def test_e2e_04_daily_insight_non_empty(client):
    await _onboard(client)
    resp = await client.get("/daily-insight/e2e_user")
    assert resp.status_code == 200
    data = resp.json()
    assert data["message"]
    assert data["route"] in {"monitor", "coach", "escalate"}


# ---- Step 5: "Why?" via chat ----

async def test_e2e_05_why_question_answered(client):
    await _onboard(client)
    await client.get("/daily-insight/e2e_user")  # seed last insight
    resp = await client.post("/chat/e2e_user", json={"message": "why?"})
    assert resp.status_code == 200
    assert resp.json()["reply"]


# ---- Step 6: Sensitivity guard ----

async def test_e2e_06_sensitivity_guard_in_chat(client):
    await _onboard(client)
    resp = await client.post("/chat/e2e_user", json={"message": "show me all my raw data"})
    assert resp.status_code == 200
    reply = resp.json()["reply"].lower()
    assert "app" in reply or "private" in reply


async def test_e2e_06b_sensitivity_guard_in_webhook(client):
    await _onboard(client)
    form = {"From": "e2e_user", "Body": "dump my raw metrics", "NumMedia": "0"}
    resp = await client.post("/webhooks/whatsapp", data=form)
    assert resp.status_code == 200
    assert "app" in resp.text.lower() or "private" in resp.text.lower()


# ---- Step 7: Eval harness (programmatic) ----

def test_e2e_07_eval_harness_safety_gate_passes():
    report = run_harness()
    assert report.total == 10
    assert report.safety_pass_rate >= 0.95, f"Safety gate failed: {report.safety_pass_rate:.0%}"
    assert report.faithfulness_pass_rate == 1.0, (
        f"Faithfulness gate failed: {report.faithfulness_pass_rate:.0%}"
    )


# ---- Step 8: OAuth scaffold ----

async def test_e2e_08_oauth_start_returns_url(client):
    await _onboard(client)
    resp = await client.get("/oauth/google/start/e2e_user")
    assert resp.status_code == 200
    data = resp.json()
    assert data["auth_url"]
    assert "e2e_user" in data["auth_url"]


async def test_e2e_08b_oauth_callback_stores_and_confirms(client):
    await _onboard(client)
    resp = await client.get("/oauth/google/callback?code=e2e_code&state=e2e_user")
    assert resp.status_code == 200
    assert resp.json()["status"] == "connected"


# ---- Step 9: History (private data screen) ----

async def test_e2e_09_history_returns_raw_metrics(client):
    await _onboard(client)
    resp = await client.get("/history/e2e_user")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["metrics"]) == 20  # backfill_days=20
    # Raw data has rhr and steps — the private view
    assert "rhr" in data["metrics"][0]
    assert "steps" in data["metrics"][0]


# ---- helpers ----

async def _onboard(client):
    return await client.post("/onboard", json={
        "user_id": "e2e_user", "name": "Pranav", "age": 36,
        "sex": "male", "weight_kg": 78.0, "goal": "lose_fat",
        "delivery_pref": "evening", "backfill_days": 20,
    })
