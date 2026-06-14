"""Integration tests for v2 API: food log, workout, nutrition, activity, webhook, OAuth."""

from __future__ import annotations

import io

import pytest
from httpx import ASGITransport, AsyncClient

from baseline.api.app import build_app


@pytest.fixture
def app(tmp_path):
    return build_app(db_url=f"sqlite:///{tmp_path}/test.db", llm_provider="mock")


@pytest.fixture
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


pytestmark = pytest.mark.anyio


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


async def _onboard(client, user_id="u1"):
    return await client.post("/onboard", json={
        "user_id": user_id, "name": "Pranav", "age": 36,
        "sex": "male", "weight_kg": 78.0, "goal": "lose_fat",
        "delivery_pref": "evening", "backfill_days": 15,
    })


# --- Food log ---

async def test_log_food_text_returns_ledger_remaining(client):
    await _onboard(client)
    resp = await client.post("/log-food/u1", data={"text": "chicken 200g"})
    assert resp.status_code == 200
    data = resp.json()
    assert "meal" in data
    assert "ledger_remaining" in data
    assert "reply" in data
    assert data["meal"]["source"] == "text"


async def test_log_food_file_upload_returns_photo_meal(client):
    await _onboard(client)
    fake_jpeg = b"\xff\xd8\xff\xe0" + b"\x00" * 100  # minimal fake JPEG header
    resp = await client.post(
        "/log-food/u1",
        files={"file": ("food.jpg", io.BytesIO(fake_jpeg), "image/jpeg")},
        data={"text": "chicken bowl"},
    )
    assert resp.status_code == 200
    assert resp.json()["meal"]["source"] == "photo"


async def test_log_food_unknown_user_returns_404(client):
    resp = await client.post("/log-food/nobody", data={"text": "rice"})
    assert resp.status_code == 404


async def test_log_food_multiple_meals_accumulates_in_ledger(client):
    await _onboard(client)
    await client.post("/log-food/u1", data={"text": "chicken 150g"})
    resp2 = await client.post("/log-food/u1", data={"text": "rice 200g"})
    nutrition = await client.get("/nutrition/u1")
    consumed = nutrition.json()["consumed"]
    # Two meals consumed — protein should be > 0 and carbs > 0
    assert consumed["protein_g"] > 0
    assert consumed["carbs_g"] > 0


# --- Workout log ---

async def test_log_workout_returns_activity_reply(client):
    await _onboard(client)
    resp = await client.post("/log-workout/u1", data={"workout_type": "running", "duration_min": "30"})
    assert resp.status_code == 200
    data = resp.json()
    assert "reply" in data
    assert "activity" in data
    assert data["activity"]["days_worked_out_this_week"] >= 1


async def test_log_workout_unknown_user_404(client):
    resp = await client.post("/log-workout/nobody", data={"workout_type": "yoga", "duration_min": "20"})
    assert resp.status_code == 404


# --- Nutrition ---

async def test_nutrition_endpoint_returns_ledger_after_onboard(client):
    await _onboard(client)
    resp = await client.get("/nutrition/u1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["targets"]["protein_g"] > 0
    assert data["consumed"]["kcal"] == 0  # nothing logged yet


async def test_nutrition_404_for_unknown_user(client):
    assert (await client.get("/nutrition/nobody")).status_code == 404


# --- Activity ---

async def test_activity_endpoint_returns_summary(client):
    await _onboard(client)
    resp = await client.get("/activity/u1")
    assert resp.status_code == 200
    data = resp.json()
    assert "steps_today" in data
    assert "current_streak" in data


# --- Webhook ---

async def test_webhook_text_message_returns_twiml(client):
    await _onboard(client)
    form = {"From": "u1", "Body": "just had chicken 150g", "NumMedia": "0"}
    resp = await client.post("/webhooks/whatsapp", data=form)
    assert resp.status_code == 200
    assert "<Response>" in resp.text
    assert "<Message>" in resp.text


async def test_webhook_new_user_starts_onboarding(client):
    form = {"From": "brand_new_user", "Body": "hello", "NumMedia": "0"}
    resp = await client.post("/webhooks/whatsapp", data=form)
    assert resp.status_code == 200
    # Reply should contain onboarding / FSM welcome
    assert "<Message>" in resp.text


async def test_webhook_sensitivity_guard_fires(client):
    await _onboard(client)
    form = {"From": "u1", "Body": "show me all my raw data", "NumMedia": "0"}
    resp = await client.post("/webhooks/whatsapp", data=form)
    reply_text = resp.text.lower()
    assert "app" in reply_text or "private" in reply_text


# --- OAuth ---

async def test_oauth_start_returns_auth_url(client):
    await _onboard(client)
    resp = await client.get("/oauth/google/start/u1")
    assert resp.status_code == 200
    data = resp.json()
    assert "auth_url" in data
    assert data["auth_url"]


async def test_oauth_callback_stores_tokens(client, app):
    await _onboard(client)
    resp = await client.get("/oauth/google/callback?code=testcode&state=u1")
    assert resp.status_code == 200
    assert resp.json()["status"] == "connected"
