"""SingleKey ID login (OAuth with PKCE) and token refresh for POINTTAPI.

The login is the one the Bosch HomeCom Easy app uses. Its redirect goes to the
app's own `com.bosch.tt.dashtt.pointt://` scheme, which a browser cannot
follow, so the user copies the callback URL (or just the code) and the
consumer passes it to extract_code_from_callback_url.

Tokens are returned to the caller and never logged or written anywhere.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import re
import secrets
import urllib.parse
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import unquote, urlencode

import aiohttp

from bosch_thermostat_client.exceptions import (
    DeviceConnectionError,
    DeviceException,
    FailedAuthException,
)

_LOGGER = logging.getLogger(__name__)

TOKEN_URL = "https://singlekey-id.com/auth/connect/token"
CLIENT_ID = "762162C0-FA2D-4540-AE66-6489F189FADC"
REDIRECT_URI = "com.bosch.tt.dashtt.pointt://app/login"
# The fixed verifier the earlier POINTTAPI work used. Consumers should pass
# their own from generate_code_verifier(); this stays the default so a login
# started with it can still finish.
CODE_VERIFIER = "abcdefghijklmnopqrstuvwxyz0123456789abcdefghijklm"
SCOPES = [
    "openid",
    "email",
    "profile",
    "offline_access",
    "pointt.gateway.claiming",
    "pointt.gateway.removal",
    "pointt.gateway.list",
    "pointt.gateway.users",
    "pointt.gateway.resource.dashapp",
    "pointt.castt.flow.token-exchange",
    "bacon",
]
# Refresh this long before the access token expires.
REFRESH_MARGIN_SECONDS = 300


def generate_code_verifier() -> str:
    """Return a fresh PKCE code verifier (RFC 7636, 43 to 128 characters)."""
    return secrets.token_urlsafe(48)


def build_auth_url(code_verifier: str = CODE_VERIFIER) -> str:
    """Build the SingleKey ID login URL for the user to open in a browser.

    Pass the same code_verifier to exchange_code_for_tokens afterwards.
    """
    code_challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode("utf-8")).digest())
        .decode("utf-8")
        .rstrip("=")
    )
    query_params = {
        "redirect_uri": urllib.parse.quote_plus(REDIRECT_URI),
        "client_id": CLIENT_ID,
        "response_type": "code",
        "prompt": "login",
        "state": "_yUmSV3AjUTXfn6DSZQZ-g",
        "nonce": "5iiIvx5_9goDrYwxxUEorQ",
        "scope": urllib.parse.quote(" ".join(SCOPES)),
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "style_id": "tt_bsch",
        "suppressed_prompt": "login",
    }
    query = urllib.parse.quote(unquote(urlencode(query_params)))
    return_url_part = urllib.parse.quote_plus("/auth/connect/authorize/callback?")
    return (
        f"https://singlekey-id.com/auth/en-us/login?ReturnUrl={return_url_part}{query}"
    )


def extract_code_from_callback_url(url: str | None) -> str | None:
    """Extract the authorization code from what the user pasted.

    Accepts the full callback URL (`com.bosch.tt.dashtt.pointt://app/login?code=...`),
    a bare query string copied from browser dev tools (`code=...&state=...`),
    or the code on its own.
    """
    text = (url or "").strip()
    if not text:
        return None
    if "code=" in text:
        try:
            # urlparse().query is empty for a bare `code=...` string (no
            # scheme), so parse the whole string as a query then.
            query = urllib.parse.urlparse(text).query or text
            codes = urllib.parse.parse_qs(query).get("code")
            return codes[0] if codes else None
        except ValueError:
            _LOGGER.debug("Failed to parse callback URL")
            return None
    # Without `code=`, a clean token is the code itself. Anything with URL or
    # query delimiters but no code is not.
    if not re.search(r"[\s?&/:]", text):
        return text
    return None


def _tokens(out: dict, refresh_token: str | None = None) -> dict[str, Any]:
    expires_at = datetime.now(timezone.utc) + timedelta(
        seconds=out.get("expires_in", 3600)
    )
    return {
        "access_token": out["access_token"],
        "refresh_token": out.get("refresh_token") or refresh_token,
        "expires_at": expires_at.isoformat(),
    }


async def _post_token(session, data: dict, what: str) -> tuple[int, Any]:
    """POST to the token endpoint; return (status, parsed JSON or None)."""
    try:
        async with session.post(TOKEN_URL, data=data) as resp:
            if resp.status != 200:
                return resp.status, None
            return resp.status, await resp.json()
    except (aiohttp.ClientConnectionError, TimeoutError) as err:
        raise DeviceConnectionError(f"POINTTAPI {what}: {err}") from err
    except (aiohttp.ClientError, ValueError) as err:
        raise DeviceException(f"POINTTAPI {what}: {err}") from err


async def exchange_code_for_tokens(
    session, code: str, code_verifier: str = CODE_VERIFIER
) -> dict[str, Any]:
    """Exchange an authorization code for tokens.

    Returns {"access_token", "refresh_token", "expires_at" (ISO 8601)}.
    Raises FailedAuthException when the code is refused.
    """
    data = {
        "grant_type": "authorization_code",
        "scope": " ".join(SCOPES),
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "client_id": CLIENT_ID,
        "code_verifier": code_verifier,
    }
    status, out = await _post_token(session, data, "token exchange")
    if status != 200:
        _LOGGER.warning("POINTTAPI token exchange failed: HTTP %s", status)
        raise FailedAuthException(
            "OAuth token exchange failed. Try the callback URL again."
        )
    if (
        not isinstance(out, dict)
        or "access_token" not in out
        or "refresh_token" not in out
    ):
        raise FailedAuthException(
            "OAuth response incomplete. Try the login step again."
        )
    return _tokens(out)


async def refresh_access_token(session, refresh_token: str) -> dict[str, Any]:
    """Get a new access token with the refresh token.

    Raises FailedAuthException when the refresh token is refused (HTTP 400 or
    401): the user has to log in again. Raises DeviceException on a server
    error and DeviceConnectionError on a network error: worth retrying.
    """
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "scope": " ".join(SCOPES),
        "client_id": CLIENT_ID,
    }
    status, out = await _post_token(session, data, "token refresh")
    if status in (400, 401):
        _LOGGER.warning("POINTTAPI token refresh refused (HTTP %s)", status)
        raise FailedAuthException("Token expired or revoked. Please log in again.")
    if status != 200:
        raise DeviceException(f"POINTTAPI token refresh failed: HTTP {status}")
    if not isinstance(out, dict) or "access_token" not in out:
        raise FailedAuthException(
            "Token refresh response invalid. Please log in again."
        )
    return _tokens(out, refresh_token)


def is_token_expired(
    expires_at: str | None, margin_seconds: int = REFRESH_MARGIN_SECONDS
) -> bool:
    """Return True if the token is expired or within margin_seconds of it."""
    if not expires_at:
        return True
    try:
        expiry = datetime.fromisoformat(expires_at)
        return datetime.now(timezone.utc) >= expiry - timedelta(seconds=margin_seconds)
    except (TypeError, ValueError):
        return True


class PoinTTAPIAuth:
    """Hold the tokens and refresh them before they expire.

    Pass async_get_access_token as PoinTTAPIClient's token_callback.
    on_refresh is called with the new token dict after every refresh, so the
    consumer can store it (Home Assistant: in the config entry).
    """

    def __init__(
        self,
        session,
        access_token: str | None,
        refresh_token: str | None,
        expires_at: str | None,
        on_refresh: Callable[[dict[str, Any]], None] | None = None,
    ):
        self._session = session
        self._access_token = access_token
        self._refresh_token = refresh_token
        self._expires_at = expires_at
        self._on_refresh = on_refresh

    async def async_get_access_token(self) -> str:
        """Return a valid access token, refreshing it when it is about to expire.

        When a refresh fails for a passing reason (server or network error)
        and the current token has not expired yet, the current token is used
        and the next call tries again.
        """
        if not self._refresh_token:
            raise FailedAuthException("No refresh token. Please log in again.")
        if not is_token_expired(self._expires_at):
            return self._access_token or ""
        try:
            tokens = await refresh_access_token(self._session, self._refresh_token)
        except DeviceException:
            if self._access_token and not is_token_expired(self._expires_at, 0):
                _LOGGER.info(
                    "POINTTAPI token refresh failed; current token still valid"
                )
                return self._access_token
            raise
        self._access_token = tokens["access_token"]
        self._refresh_token = tokens["refresh_token"]
        self._expires_at = tokens["expires_at"]
        if self._on_refresh:
            self._on_refresh(tokens)
        return self._access_token
