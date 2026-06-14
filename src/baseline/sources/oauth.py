"""OAuth provider abstraction — used by the Google Health connect flow.

Tests run against ``MockOAuthProvider`` (no network). Real Google OAuth is wired
by setting ``GOOGLE_CLIENT_ID`` / ``GOOGLE_CLIENT_SECRET`` in the environment.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class OAuthProvider(Protocol):
    def authorization_url(self, user_id: str, redirect_uri: str) -> str:
        """Return the URL the user should visit to authorise access."""
        ...

    def exchange_code(self, code: str, redirect_uri: str) -> dict:
        """Exchange an authorisation code for access + refresh tokens."""
        ...

    def refresh(self, tokens: dict) -> dict:
        """Refresh an expired access token; return updated token dict."""
        ...


class MockOAuthProvider:
    """Deterministic stub — returns fixed fake tokens without any network call."""

    FAKE_URL = "https://accounts.google.com/o/oauth2/auth?mock=1"
    FAKE_TOKENS = {
        "access_token": "mock_access_token",
        "refresh_token": "mock_refresh_token",
        "expires_in": 3600,
        "token_type": "Bearer",
    }

    def authorization_url(self, user_id: str, redirect_uri: str) -> str:
        return f"{self.FAKE_URL}&state={user_id}"

    def exchange_code(self, code: str, redirect_uri: str) -> dict:
        return dict(self.FAKE_TOKENS)

    def refresh(self, tokens: dict) -> dict:
        refreshed = dict(tokens)
        refreshed["access_token"] = "mock_refreshed_access_token"
        return refreshed


class GoogleOAuthProvider:
    """Real Google OAuth 2.0 via google-auth-oauthlib (optional dependency)."""

    _SCOPES = [
        "https://www.googleapis.com/auth/fitness.activity.read",
        "https://www.googleapis.com/auth/fitness.heart_rate.read",
        "https://www.googleapis.com/auth/fitness.sleep.read",
        "https://www.googleapis.com/auth/fitness.body.read",
    ]

    def __init__(self, client_id: str, client_secret: str) -> None:
        try:
            from google_auth_oauthlib.flow import Flow as _Flow  # noqa: F401
        except ImportError as e:
            raise ImportError(
                "google-auth-oauthlib is required for real Google OAuth. "
                "Install it with: pip install google-auth-oauthlib"
            ) from e
        self._client_id = client_id
        self._client_secret = client_secret

    def _make_flow(self, redirect_uri: str):
        from google_auth_oauthlib.flow import Flow

        return Flow.from_client_config(
            {
                "web": {
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                }
            },
            scopes=self._SCOPES,
            redirect_uri=redirect_uri,
        )

    def authorization_url(self, user_id: str, redirect_uri: str) -> str:
        flow = self._make_flow(redirect_uri)
        url, _ = flow.authorization_url(
            access_type="offline", state=user_id, prompt="consent"
        )
        return url

    def exchange_code(self, code: str, redirect_uri: str) -> dict:
        flow = self._make_flow(redirect_uri)
        flow.fetch_token(code=code)
        creds = flow.credentials
        return {
            "access_token": creds.token,
            "refresh_token": creds.refresh_token,
            "expires_in": 3600,
            "token_type": "Bearer",
        }

    def refresh(self, tokens: dict) -> dict:
        import google.auth.transport.requests
        import google.oauth2.credentials

        creds = google.oauth2.credentials.Credentials(
            token=tokens["access_token"],
            refresh_token=tokens.get("refresh_token"),
            token_uri="https://oauth2.googleapis.com/token",
            client_id=self._client_id,
            client_secret=self._client_secret,
        )
        creds.refresh(google.auth.transport.requests.Request())
        return {**tokens, "access_token": creds.token}


def build_oauth_provider(client_id: str | None, client_secret: str | None) -> OAuthProvider:
    if client_id and client_secret:
        return GoogleOAuthProvider(client_id, client_secret)
    return MockOAuthProvider()
