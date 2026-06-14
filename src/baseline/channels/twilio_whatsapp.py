"""Twilio WhatsApp channel adapter.

Handles:
- Outbound: ``send_text`` via Twilio REST messages.create.
- Inbound: ``parse_inbound`` converts a Twilio form-encoded webhook payload to
  an ``InboundMessage``. ``download_media`` fetches authenticated media (food photos).
- TwiML: ``make_twiml_response`` wraps a reply string for immediate in-window delivery.

The Twilio ``Client`` is injected so tests can mock it without network calls.
Signature validation is done when ``TWILIO_AUTH_TOKEN`` is available; skipped in
mock mode so the test suite never touches Twilio.
"""

from __future__ import annotations

from xml.sax.saxutils import escape as xml_escape

from baseline.channels.base import InboundMessage


class TwilioWhatsAppChannel:
    def __init__(
        self,
        account_sid: str,
        auth_token: str,
        from_number: str,
        client=None,  # twilio.rest.Client — injected for tests
    ) -> None:
        self._account_sid = account_sid
        self._auth_token = auth_token
        self._from = from_number
        self._client = client  # lazy-loaded when None

    def _get_client(self):
        if self._client is None:
            from twilio.rest import Client
            self._client = Client(self._account_sid, self._auth_token)
        return self._client

    def send_text(self, user_id: str, text: str) -> None:
        self._get_client().messages.create(
            from_=self._from,
            to=user_id,
            body=text,
        )

    def send_buttons(self, user_id: str, text: str, buttons: list[str]) -> None:
        body = text + "\n" + "\n".join(f"  {i+1}. {b}" for i, b in enumerate(buttons))
        self.send_text(user_id, body)

    def parse_inbound(self, form_data: dict) -> InboundMessage:
        """Convert a Twilio webhook form dict to an InboundMessage."""
        user_id = form_data.get("From", "")
        body = form_data.get("Body", "") or None
        num_media = int(form_data.get("NumMedia", "0"))
        media_url = form_data.get("MediaUrl0") if num_media > 0 else None
        caption = body if (num_media > 0 and body) else None
        text = body if num_media == 0 else None
        return InboundMessage(
            user_id=user_id,
            text=text,
            media_url=media_url,
            caption=caption,
        )

    def download_media(self, media_url: str) -> bytes:
        """Download authenticated Twilio media (e.g. a food photo)."""
        import urllib.request
        import base64

        password_mgr = urllib.request.HTTPPasswordMgrWithDefaultRealm()
        password_mgr.add_password(None, media_url, self._account_sid, self._auth_token)
        handler = urllib.request.HTTPBasicAuthHandler(password_mgr)
        opener = urllib.request.build_opener(handler)
        with opener.open(media_url, timeout=10) as resp:
            return resp.read()

    @staticmethod
    def make_twiml_response(message: str) -> str:
        """Wrap a reply in TwiML for same-request delivery (inside 24h window)."""
        safe = xml_escape(message)
        return f"<?xml version='1.0' encoding='UTF-8'?><Response><Message>{safe}</Message></Response>"

    def validate_signature(self, url: str, params: dict, signature: str) -> bool:
        """Verify the X-Twilio-Signature header. Returns True when auth token is set."""
        if not self._auth_token:
            return True  # mock/test mode — skip validation
        from twilio.request_validator import RequestValidator
        return RequestValidator(self._auth_token).validate(url, params, signature)
