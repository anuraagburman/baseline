"""Tests for the OAuth provider protocol + GoogleHealthSource fallback."""

from __future__ import annotations

import pytest

from baseline.channels.local import LocalChannel
from baseline.sources.oauth import (
    MockOAuthProvider,
    OAuthProvider,
    build_oauth_provider,
)
from baseline.sources.google import GoogleHealthSource
from baseline.storage.db import Database
from baseline.storage import repository as repo
from baseline.domain.models import Goal, Sex, UserProfile


@pytest.fixture
def db(tmp_path):
    database = Database(f"sqlite:///{tmp_path}/test.db")
    database.create_all()
    with database.session() as s:
        repo.upsert_user(s, UserProfile(user_id="u1", age=36, sex=Sex.MALE,
                                         weight_kg=78.0, goal=Goal.LOSE_FAT))
    return database


def test_mock_satisfies_protocol():
    assert isinstance(MockOAuthProvider(), OAuthProvider)


def test_mock_authorization_url_contains_state():
    url = MockOAuthProvider().authorization_url("u1", "http://localhost/cb")
    assert "u1" in url


def test_mock_exchange_code_returns_tokens():
    tokens = MockOAuthProvider().exchange_code("abc", "http://localhost/cb")
    assert "access_token" in tokens
    assert "refresh_token" in tokens


def test_mock_refresh_updates_access_token():
    tokens = MockOAuthProvider().FAKE_TOKENS.copy()
    refreshed = MockOAuthProvider().refresh(tokens)
    assert refreshed["access_token"] != tokens["access_token"]


def test_build_oauth_provider_returns_mock_when_no_creds():
    provider = build_oauth_provider(None, None)
    assert isinstance(provider, MockOAuthProvider)


def test_oauth_full_roundtrip_stores_tokens(db):
    provider = MockOAuthProvider()
    channel = LocalChannel()
    url = provider.authorization_url("u1", "http://localhost/cb")
    assert url

    tokens = provider.exchange_code("code", "http://localhost/cb")
    with db.session() as s:
        repo.save_oauth_tokens(s, "u1", "google", tokens)
    with db.session() as s:
        stored = repo.get_oauth_tokens(s, "u1", "google")
    assert stored["access_token"] == tokens["access_token"]


def test_google_health_source_falls_back_to_synthetic_without_tokens(db):
    from datetime import date
    gs = GoogleHealthSource(db=db, user_id="u1")
    m = gs.fetch_day("u1", date(2026, 6, 14))
    # Synthetic fallback always returns valid data
    assert m.rhr > 0
    assert m.steps >= 0


def test_google_health_source_falls_back_gracefully_with_expired_tokens(db):
    from datetime import date
    # Store a fake token that will fail to make real API calls
    with db.session() as s:
        repo.save_oauth_tokens(s, "u1", "google",
                               {"access_token": "expired", "refresh_token": "old"})
    gs = GoogleHealthSource(db=db, user_id="u1")
    # Should fall back to synthetic, not raise
    m = gs.fetch_day("u1", date(2026, 6, 14))
    assert m.rhr > 0
