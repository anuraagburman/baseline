"""Tests for the proactive daily-nudge endpoint (POST /cron/daily-nudge)."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from httpx import ASGITransport, AsyncClient

from baseline.api.app import build_app
from baseline.domain.models import Goal, OnboardingState, Sex, UserProfile
from baseline.ingestion.pipeline import ingest_range
from baseline.sources.synthetic import SyntheticHealthSource
from baseline.storage import repository as repo
from baseline.storage.db import Database

CRON_SECRET = "test-cron-secret"


@pytest.fixture
def app(tmp_path):
    return build_app(
        db_url=f"sqlite:///{tmp_path}/test.db",
        llm_provider="mock",
        cron_secret=CRON_SECRET,
    )


@pytest.fixture
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


pytestmark = pytest.mark.anyio


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


def _seed(app, user_id, opted_in, delivery_pref="both", days=20):
    # Reach into the app's DB via the same URL by re-opening it.
    # build_app created the DB + schema; grab it through a fresh Database on same file.
    db: Database = app.state.db  # exposed for tests
    profile = UserProfile(user_id=user_id, name="P", age=36, sex=Sex.MALE,
                          weight_kg=78.0, goal=Goal.LOSE_FAT,
                          delivery_pref=delivery_pref, opted_in=opted_in)
    with db.session() as s:
        repo.upsert_user(s, profile)
        repo.save_onboarding_state(s, OnboardingState(user_id=user_id, step="done",
                                                      data={}, complete=True))
    today = date.today()
    ingest_range(db, SyntheticHealthSource(), user_id, today - timedelta(days=days - 1), today)


async def test_healthz_ok(client):
    resp = await client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


async def test_cron_requires_secret(client):
    resp = await client.post("/cron/daily-nudge")
    assert resp.status_code == 403


async def test_cron_rejects_wrong_secret(client):
    resp = await client.post("/cron/daily-nudge", headers={"X-Cron-Secret": "wrong"})
    assert resp.status_code == 403


async def test_cron_sends_nudge_to_opted_in_user(client, app):
    _seed(app, "opted", opted_in=True)
    resp = await client.post("/cron/daily-nudge", headers={"X-Cron-Secret": CRON_SECRET})
    assert resp.status_code == 200
    data = resp.json()
    assert data["sent"] == 1
    # The channel captured a templated nudge for the opted-in user
    channel = app.state.channel
    assert any(uid == "opted" for uid, _ in channel.sent)


async def test_cron_skips_non_opted_in_user(client, app):
    _seed(app, "opted", opted_in=True)
    _seed(app, "silent", opted_in=False)
    resp = await client.post("/cron/daily-nudge", headers={"X-Cron-Secret": CRON_SECRET})
    sent_ids = {uid for uid, _ in app.state.channel.sent}
    assert "opted" in sent_ids
    assert "silent" not in sent_ids


async def test_cron_window_filters_delivery_pref(client, app):
    _seed(app, "morning_user", opted_in=True, delivery_pref="morning")
    _seed(app, "evening_user", opted_in=True, delivery_pref="evening")
    resp = await client.post("/cron/daily-nudge?window=morning",
                             headers={"X-Cron-Secret": CRON_SECRET})
    sent_ids = {uid for uid, _ in app.state.channel.sent}
    assert "morning_user" in sent_ids
    assert "evening_user" not in sent_ids
