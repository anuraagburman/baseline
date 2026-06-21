"""Layman guarantees: food photo over WhatsApp + every action gets a contextual reply."""

from __future__ import annotations

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
        "user_id": user_id, "name": "Pranav", "age": 36, "sex": "male",
        "weight_kg": 78.0, "goal": "lose_fat", "backfill_days": 15,
    })


def _reply(resp) -> str:
    """Extract the message text from the webhook's TwiML response."""
    return resp.text


# --- Step 6: food photo over WhatsApp ---

async def test_food_photo_webhook_returns_macros(client):
    await _onboard(client)
    form = {"From": "u1", "Body": "chicken bowl", "NumMedia": "1",
            "MediaUrl0": "https://api.twilio.com/media/abc",
            "MediaContentType0": "image/jpeg"}
    resp = await client.post("/webhooks/whatsapp", data=form)
    assert resp.status_code == 200
    body = _reply(resp).lower()
    assert "logged" in body or "protein" in body or "kcal" in body


async def test_food_photo_no_caption_still_logs(client):
    await _onboard(client)
    form = {"From": "u1", "NumMedia": "1",
            "MediaUrl0": "https://api.twilio.com/media/xyz",
            "MediaContentType0": "image/jpeg"}
    resp = await client.post("/webhooks/whatsapp", data=form)
    body = _reply(resp).lower()
    assert "logged" in body or "protein" in body or "kcal" in body


# --- Step 7: every action gets a non-empty, on-topic reply ---

@pytest.mark.parametrize("body,expect_any", [
    ("just had chicken and rice", ["protein", "kcal", "logged"]),       # food text
    ("just ran for 30 minutes", ["streak", "workout", "step"]),          # workout
    ("why?", ["your", "data", "rate", "sleep", "usual", "baseline"]),    # coaching
    ("show me all my raw data", ["app", "private"]),                     # privacy guard
    ("help", ["meal", "workout", "log", "coach", "photo"]),             # help → menu
    ("stop", ["paused", "stop", "won't"]),                              # opt-out
])
async def test_every_action_gets_contextual_reply(client, body, expect_any):
    await _onboard(client)
    # seed an insight so "why?" has context
    await client.get("/daily-insight/u1")
    resp = await client.post("/webhooks/whatsapp",
                             data={"From": "u1", "Body": body, "NumMedia": "0"})
    assert resp.status_code == 200
    reply = _reply(resp).lower()
    assert reply.strip(), "reply must never be empty"
    assert any(tok in reply for tok in expect_any), f"{body!r} -> {reply!r}"


async def test_unknown_input_never_says_didnt_understand(client):
    await _onboard(client)
    resp = await client.post("/webhooks/whatsapp",
                             data={"From": "u1", "Body": "xyzzy qwerty", "NumMedia": "0"})
    reply = _reply(resp).lower()
    assert "didn't understand" not in reply
    assert "i don't understand" not in reply
    assert reply.strip()
