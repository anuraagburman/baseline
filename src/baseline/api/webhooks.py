"""WhatsApp webhook endpoint (Twilio inbound form-post).

Receives an inbound Twilio WhatsApp message, routes it through the conversation
manager, and responds with TwiML for immediate in-window delivery (free 24h
session). Media (food photos) are downloaded and passed as bytes to the router.

Twilio signature validation is active when ``TWILIO_AUTH_TOKEN`` is set;
skipped automatically in test/LocalChannel mode.
"""

from __future__ import annotations

from fastapi import APIRouter, Form, Header, Request, Response
from fastapi.responses import PlainTextResponse

from baseline.channels.base import InboundMessage


def make_webhook_router(manager, channel, db) -> APIRouter:
    """Factory — returns a router with the manager/channel/db already closed over."""
    router = APIRouter()

    @router.post("/webhooks/whatsapp", response_class=PlainTextResponse)
    async def whatsapp_webhook(
        request: Request,
        x_twilio_signature: str | None = Header(default=None),
    ):
        form = await request.form()
        form_data = dict(form)

        # Parse inbound (LocalChannel in tests, Twilio in prod).
        from baseline.channels.twilio_whatsapp import TwilioWhatsAppChannel
        if isinstance(channel, TwilioWhatsAppChannel):
            # Validate Twilio signature when token is set.
            if not channel.validate_signature(str(request.url), form_data,
                                               x_twilio_signature or ""):
                return Response(content="Forbidden", status_code=403)
            inbound = channel.parse_inbound(form_data)
            if inbound.media_url:
                try:
                    inbound.media_bytes = channel.download_media(inbound.media_url)
                except Exception:
                    pass  # if media download fails, estimator will use caption only
        else:
            # LocalChannel / test path — build InboundMessage from form dict.
            inbound = InboundMessage(
                user_id=form_data.get("From", "test_user"),
                text=form_data.get("Body") or None,
                media_url=form_data.get("MediaUrl0"),
                caption=form_data.get("Body") if form_data.get("NumMedia", "0") != "0" else None,
            )

        # Look up the profile.
        from baseline.storage import repository as repo
        with db.session() as s:
            profile = repo.get_user(s, inbound.user_id)

        if profile is None:
            # New user — start onboarding and create a stub profile.
            from baseline.domain.models import Goal, Sex, UserProfile
            profile = UserProfile(
                user_id=inbound.user_id, age=30, sex=Sex.OTHER,
                weight_kg=70.0, goal=Goal.GENERAL_HEALTH,
            )
            with db.session() as s:
                repo.upsert_user(s, profile)

        reply = manager.handle(inbound, profile)

        # Send via channel (Twilio REST) and also return TwiML for instant delivery.
        channel.send_text(inbound.user_id, reply)
        if isinstance(channel, TwilioWhatsAppChannel):
            twiml = channel.make_twiml_response(reply)
        else:
            twiml = f"<Response><Message>{reply}</Message></Response>"
        return PlainTextResponse(content=twiml, media_type="text/xml")

    return router
