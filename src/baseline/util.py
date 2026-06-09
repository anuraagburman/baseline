"""Small shared utilities."""

from __future__ import annotations

from datetime import datetime, timezone


def utcnow() -> datetime:
    """Timezone-aware current UTC time (replaces the deprecated ``utcnow``)."""
    return datetime.now(timezone.utc)
