"""Google Health OAuth endpoints.

GET /oauth/google/start/{user_id}     — returns JSON {auth_url, wa_deep_link} +
                                        a QR code PNG (image/png accept) pointing
                                        to the OAuth URL so the user can scan and
                                        authorise from their phone.
GET /oauth/google/callback            — receives the Google redirect, stores tokens,
                                        sends the user a WhatsApp confirmation.
"""

from __future__ import annotations

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse, Response


def make_oauth_router(oauth_provider, db, channel, wa_number: str | None = None) -> APIRouter:
    router = APIRouter()

    @router.get("/oauth/google/start/{user_id}")
    async def start_oauth(user_id: str, accept: str | None = None):
        from baseline.config import get_settings

        s = get_settings()
        redirect_uri = s.google_oauth_redirect_uri
        auth_url = oauth_provider.authorization_url(user_id, redirect_uri)
        wa_link = f"https://wa.me/{(wa_number or '').replace('whatsapp:', '').replace('+', '')}"

        # Return PNG QR code when caller wants image/png.
        if accept and "image/png" in accept:
            import qrcode
            import io

            img = qrcode.make(auth_url)
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return Response(content=buf.getvalue(), media_type="image/png")

        return JSONResponse({"auth_url": auth_url, "wa_deep_link": wa_link, "user_id": user_id})

    @router.get("/oauth/google/callback")
    async def oauth_callback(code: str = Query(...), state: str = Query("")):
        from baseline.config import get_settings
        from baseline.storage import repository as repo

        s = get_settings()
        user_id = state  # we stash user_id in OAuth state param
        tokens = oauth_provider.exchange_code(code, s.google_oauth_redirect_uri)

        with db.session() as sess:
            repo.save_oauth_tokens(sess, user_id, "google", tokens)
            ob = repo.get_onboarding_state(sess, user_id)

        # Advance the onboarding FSM past the "connect" step if mid-flow.
        if ob and not ob.complete:
            from baseline.domain.models import OnboardingState
            advanced = OnboardingState(
                user_id=user_id, step="connect",
                data={**ob.data, "connect": "connected"}, complete=False,
            )
            with db.session() as sess:
                repo.save_onboarding_state(sess, advanced)

        msg = "✅ Connected! Your Google Health data is now linked. You'll get your first insight shortly."
        channel.send_text(user_id, msg)
        return JSONResponse({"status": "connected", "user_id": user_id})

    return router
