"""Application configuration, driven by environment variables.

Every external dependency in Baseline sits behind an interface; this module
holds the knobs that decide which concrete implementation is wired in (e.g.
mock vs. real LLM) and the parameters of the analytics engine.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-driven settings with sane local defaults.

    Read from a ``.env`` file or process environment, all prefixed with
    ``BASELINE_`` (except ``ANTHROPIC_API_KEY``, which keeps its conventional name).
    """

    model_config = SettingsConfigDict(
        env_prefix="BASELINE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- LLM ---
    llm_provider: str = "mock"  # "mock" | "claude"
    claude_model: str = "claude-opus-4-8"
    anthropic_api_key: str | None = None

    # --- Storage ---
    db_url: str = "sqlite:///baseline.db"

    # --- Baseline engine ---
    window_days: int = 28
    min_history_days: int = 14
    backfill_days: int = 45

    # --- Triage ---
    deviation_threshold: float = 2.0  # |z| below which a metric is "monitor"

    # --- Twilio WhatsApp (optional; absent → LocalChannel used) ---
    twilio_account_sid: str | None = None
    twilio_auth_token: str | None = None
    twilio_whatsapp_from: str = "whatsapp:+14155238886"  # Twilio sandbox default

    # --- Google OAuth (optional; absent → MockOAuthProvider used) ---
    google_client_id: str | None = None
    google_client_secret: str | None = None
    google_oauth_redirect_uri: str = "http://localhost:8000/oauth/google/callback"

    # --- Vision / nutrition estimator ---
    vision_provider: str = "mock"  # "mock" | "claude"


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance.

    Reads ``ANTHROPIC_API_KEY`` (unprefixed) as a fallback so the conventional
    env var name works alongside the ``BASELINE_`` prefix.
    """
    import os

    settings = Settings()
    if settings.anthropic_api_key is None:
        settings.anthropic_api_key = os.environ.get("ANTHROPIC_API_KEY")
    return settings
