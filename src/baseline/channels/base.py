"""Channel abstraction — the contract every delivery adapter implements.

Downstream code (router, webhook, CLI) only sees ``Channel`` and ``InboundMessage``.
Swapping WhatsApp for SMS or a web socket is a new adapter class + a config change.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass
class InboundMessage:
    """A normalised inbound message — text, media, or both."""

    user_id: str
    text: str | None = None
    media_bytes: bytes | None = None
    media_url: str | None = None
    caption: str | None = None  # text body when media is also present

    @property
    def has_media(self) -> bool:
        return self.media_bytes is not None or self.media_url is not None


@runtime_checkable
class Channel(Protocol):
    def send_text(self, user_id: str, text: str) -> None:
        """Send a plain-text message to the user."""
        ...

    def send_buttons(self, user_id: str, text: str, buttons: list[str]) -> None:
        """Send a message with quick-reply buttons (falls back to text list)."""
        ...
