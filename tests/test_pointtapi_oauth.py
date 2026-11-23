"""Tests for the POINTTAPI login and token refresh (ported from ha_bosch)."""

from __future__ import annotations

import base64
import hashlib
import urllib.parse
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import aiohttp
import pytest

from bosch_thermostat_client.exceptions import (
    DeviceConnectionError,
    DeviceException,
    FailedAuthException,
)
from bosch_thermostat_client.pointtapi import (
    PoinTTAPIAuth,
    build_auth_url,
    exchange_code_for_tokens,
    extract_code_from_callback_url,
    generate_code_verifier,
    is_token_expired,
    refresh_access_token,
)
from bosch_thermostat_client.pointtapi.oauth import CLIENT_ID


def _ctx(resp):
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=resp)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


def _session(status, body=None):
    resp = AsyncMock()
    resp.status = status
    resp.json = AsyncMock(return_value=body or {})
    session = MagicMock()
    session.post = MagicMock(return_value=_ctx(resp))
    return session


def _iso(**delta):
    return (datetime.now(timezone.utc) + timedelta(**delta)).isoformat()


class TestExtractCode:
    @pytest.mark.parametrize(
        "pasted, code",
        [
            ("com.bosch.tt.dashtt.pointt://app/login?code=ABC123&state=xyz", "ABC123"),
            ("com.bosch.tt.dashtt.pointt://app/login?code=A%20B%20C&state=x", "A B C"),
            ("  com.bosch.tt.dashtt.pointt://app/login?code=XYZ  ", "XYZ"),
            ("code=ABC-1&state=xyz", "ABC-1"),
            ("3E7A9F2B1C4D5E6F-1", "3E7A9F2B1C4D5E6F-1"),
            ("  XYZ-1  ", "XYZ-1"),
            ("com.bosch.tt.dashtt.pointt://app/login?state=xyz", None),
            ("com.bosch.tt.dashtt.pointt://app/login", None),
            ("", None),
            (None, None),
        ],
    )
    def test_extract(self, pasted, code):
        assert extract_code_from_callback_url(pasted) == code


class TestIsTokenExpired:
    @pytest.mark.parametrize("value", [None, "", "not-a-date"])
    def test_missing_or_bad_is_expired(self, value):
        assert is_token_expired(value) is True

    def test_future_past_and_margin(self):
        assert is_token_expired(_iso(hours=1)) is False
        assert is_token_expired(_iso(hours=-1)) is True
        assert is_token_expired(_iso(minutes=4)) is True  # inside the 5 min margin
        assert is_token_expired(_iso(seconds=30), margin_seconds=10) is False


class TestBuildAuthUrl:
    def test_url_shape(self):
        url = build_auth_url()
        assert url.startswith("https://singlekey-id.com/auth/en-us/login?ReturnUrl=")
        assert CLIENT_ID in url
        assert "redirect_uri" in url
        assert build_auth_url() == url

    def test_challenge_follows_the_verifier(self):
        verifier = generate_code_verifier()
        assert 43 <= len(verifier) <= 128
        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
            .decode()
            .rstrip("=")
        )
        assert challenge in urllib.parse.unquote(build_auth_url(verifier))
        assert build_auth_url(verifier) != build_auth_url()


class TestExchangeCode:
    @pytest.mark.asyncio
    async def test_success(self):
        session = _session(
            200, {"access_token": "at", "refresh_token": "rt", "expires_in": 3600}
        )
        tokens = await exchange_code_for_tokens(session, "code", code_verifier="v" * 43)
        assert tokens["access_token"] == "at"
        assert tokens["refresh_token"] == "rt"
        assert is_token_expired(tokens["expires_at"]) is False
        assert session.post.call_args.kwargs["data"]["code_verifier"] == "v" * 43

    @pytest.mark.asyncio
    async def test_refused_code_raises_failed_auth(self):
        with pytest.raises(FailedAuthException):
            await exchange_code_for_tokens(_session(400), "bad")

    @pytest.mark.asyncio
    async def test_incomplete_response_raises_failed_auth(self):
        with pytest.raises(FailedAuthException):
            await exchange_code_for_tokens(_session(200, {"id_token": "x"}), "code")


class TestRefresh:
    @pytest.mark.asyncio
    async def test_success_without_code_verifier(self):
        session = _session(
            200,
            {"access_token": "new_at", "refresh_token": "new_rt", "expires_in": 7200},
        )
        tokens = await refresh_access_token(session, "old_rt")
        assert (tokens["access_token"], tokens["refresh_token"]) == ("new_at", "new_rt")
        assert "code_verifier" not in session.post.call_args.kwargs["data"]

    @pytest.mark.asyncio
    async def test_keeps_old_refresh_token_when_none_comes_back(self):
        tokens = await refresh_access_token(
            _session(200, {"access_token": "at"}), "kept"
        )
        assert tokens["refresh_token"] == "kept"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("status", [400, 401])
    async def test_refused_raises_failed_auth(self, status):
        with pytest.raises(FailedAuthException):
            await refresh_access_token(_session(status), "rt")

    @pytest.mark.asyncio
    async def test_5xx_raises_device_exception(self):
        with pytest.raises(DeviceException):
            await refresh_access_token(_session(503), "rt")

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "error", [TimeoutError("timed out"), aiohttp.ClientConnectionError("down")]
    )
    async def test_network_error_raises_connection_error(self, error):
        session = MagicMock()
        session.post = MagicMock(side_effect=error)
        with pytest.raises(DeviceConnectionError):
            await refresh_access_token(session, "rt")

    @pytest.mark.asyncio
    async def test_missing_access_token_raises_failed_auth(self):
        with pytest.raises(FailedAuthException):
            await refresh_access_token(_session(200, {"expires_in": 3600}), "rt")


class TestPoinTTAPIAuth:
    def _auth(self, session, expires_at, access_token="old_at", refresh_token="old_rt"):
        on_refresh = MagicMock()
        auth = PoinTTAPIAuth(
            session, access_token, refresh_token, expires_at, on_refresh
        )
        return auth, on_refresh

    @pytest.mark.asyncio
    async def test_valid_token_is_returned_without_refresh(self):
        session = MagicMock()
        auth, on_refresh = self._auth(session, _iso(hours=1))
        assert await auth.async_get_access_token() == "old_at"
        session.post.assert_not_called()
        on_refresh.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_refresh_token_raises_failed_auth(self):
        auth, _ = self._auth(MagicMock(), _iso(hours=1), refresh_token="")
        with pytest.raises(FailedAuthException):
            await auth.async_get_access_token()

    @pytest.mark.asyncio
    async def test_expired_token_is_refreshed_and_reported(self):
        session = _session(
            200,
            {"access_token": "new_at", "refresh_token": "new_rt", "expires_in": 3600},
        )
        auth, on_refresh = self._auth(session, _iso(hours=-1))
        assert await auth.async_get_access_token() == "new_at"
        tokens = on_refresh.call_args.args[0]
        assert (tokens["access_token"], tokens["refresh_token"]) == ("new_at", "new_rt")
        # The new token is kept: no second refresh.
        assert await auth.async_get_access_token() == "new_at"
        assert session.post.call_count == 1

    @pytest.mark.asyncio
    async def test_passing_failure_keeps_a_still_valid_token(self):
        # Inside the refresh margin, so a refresh is tried, but not expired yet.
        auth, on_refresh = self._auth(_session(503), _iso(seconds=120))
        assert await auth.async_get_access_token() == "old_at"
        on_refresh.assert_not_called()

    @pytest.mark.asyncio
    async def test_passing_failure_with_expired_token_raises(self):
        auth, _ = self._auth(_session(503), _iso(seconds=-10))
        with pytest.raises(DeviceException):
            await auth.async_get_access_token()

    @pytest.mark.asyncio
    async def test_passing_failure_without_access_token_raises(self):
        auth, _ = self._auth(_session(503), _iso(seconds=120), access_token="")
        with pytest.raises(DeviceException):
            await auth.async_get_access_token()

    @pytest.mark.asyncio
    async def test_refused_refresh_raises_failed_auth(self):
        auth, on_refresh = self._auth(_session(401), _iso(seconds=-10))
        with pytest.raises(FailedAuthException):
            await auth.async_get_access_token()
        on_refresh.assert_not_called()
