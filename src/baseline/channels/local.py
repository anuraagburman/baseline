"""LocalChannel — a no-network channel for tests and the terminal CLI.

``sent`` captures every outbound message so tests can assert on it.
``feed`` enqueues a simulated inbound message (used by the CLI read loop).
"""

from __future__ import annotations

from baseline.channels.base import InboundMessage


class LocalChannel:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []  # (user_id, text)
        self._inbox: list[InboundMessage] = []

    def send_text(self, user_id: str, text: str) -> None:
        self.sent.append((user_id, text))

    def send_buttons(self, user_id: str, text: str, buttons: list[str]) -> None:
        combined = text + "\n" + "\n".join(f"  [{i+1}] {b}" for i, b in enumerate(buttons))
        self.sent.append((user_id, combined))

    def feed(self, user_id: str, text: str | None = None,
             media_bytes: bytes | None = None, caption: str | None = None) -> None:
        """Enqueue a simulated inbound message (for the CLI / test harness)."""
        self._inbox.append(InboundMessage(
            user_id=user_id, text=text,
            media_bytes=media_bytes, caption=caption,
        ))

    def pop_inbound(self) -> InboundMessage | None:
        return self._inbox.pop(0) if self._inbox else None

    def clear(self) -> None:
        self.sent.clear()
        self._inbox.clear()
