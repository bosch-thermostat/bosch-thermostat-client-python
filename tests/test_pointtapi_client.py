"""Tests for the POINTTAPI HTTP client (ported from ha_bosch)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import aiohttp
import pytest

from bosch_thermostat_client.exceptions import (
    DeviceConnectionError,
    DeviceException,
    FailedAuthException,
)
from bosch_thermostat_client.pointtapi import PoinTTAPIClient
from bosch_thermostat_client.pointtapi.client import (
    POINTTAPI_BASE_URL,
    POINTTAPI_BULK_URL,
)


def _ctx(resp):
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=resp)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


def _resp(status=200, body=None, content_type="application/json"):
    resp = AsyncMock()
    resp.status = status
    resp.content_type = content_type
    resp.json = AsyncMock(return_value=body)
    resp.text = AsyncMock(return_value=body if isinstance(body, str) else "")
    return resp


def _client(*responses, token="tok"):
    session = MagicMock()
    session.request = MagicMock(side_effect=[_ctx(r) for r in responses])
    token_callback = AsyncMock(return_value=token)
    return PoinTTAPIClient("123", session, token_callback), session, token_callback


class TestURL:
    def test_base_url_includes_device_id(self):
        c, _, _ = _client()
        assert c._base == f"{POINTTAPI_BASE_URL}123/resource/"
        assert c.device_id == "123"

    def test_leading_slash_is_optional(self):
        c, _, _ = _client()
        assert c._url("/gateway/DateTime") == c._url("gateway/DateTime")
        assert c._url("/gateway/DateTime").endswith("123/resource/gateway/DateTime")


class TestGet:
    @pytest.mark.asyncio
    async def test_returns_json(self):
        c, _, _ = _client(_resp(body={"id": "/gateway", "value": "ok"}))
        assert await c.get("/gateway") == {"id": "/gateway", "value": "ok"}

    @pytest.mark.asyncio
    async def test_text_fallback(self):
        c, _, _ = _client(_resp(body="plain text", content_type="text/plain"))
        assert await c.get("/gateway") == "plain text"

    @pytest.mark.asyncio
    async def test_sends_bearer_token(self):
        c, session, _ = _client(_resp(body={}), token="my_token")
        await c.get("/gateway")
        method, url = session.request.call_args.args
        assert method == "GET"
        assert session.request.call_args.kwargs["headers"]["Authorization"] == (
            "Bearer my_token"
        )

    @pytest.mark.asyncio
    @pytest.mark.parametrize("status", [401, 403])
    async def test_auth_failure_raises_failed_auth(self, status):
        c, _, _ = _client(_resp(status=status))
        with pytest.raises(FailedAuthException):
            await c.get("/gateway")

    def test_failed_auth_is_not_a_device_exception(self):
        # Consumers retry on DeviceException; an auth failure must reach them.
        assert not issubclass(FailedAuthException, DeviceException)

    @pytest.mark.asyncio
    async def test_500_raises_device_exception(self):
        c, _, _ = _client(_resp(status=500, body="oops", content_type="text/plain"))
        with pytest.raises(DeviceException, match="500"):
            await c.get("/gateway")

    @pytest.mark.asyncio
    async def test_network_error_raises_connection_error(self):
        session = MagicMock()
        session.request = MagicMock(side_effect=aiohttp.ClientConnectionError("down"))
        c = PoinTTAPIClient("123", session, AsyncMock(return_value="tok"))
        with pytest.raises(DeviceConnectionError):
            await c.get("/gateway")

    @pytest.mark.asyncio
    async def test_timeout_raises_connection_error(self):
        session = MagicMock()
        session.request = MagicMock(side_effect=TimeoutError())
        c = PoinTTAPIClient("123", session, AsyncMock(return_value="tok"))
        with pytest.raises(DeviceConnectionError):
            await c.get("/gateway")

    @pytest.mark.asyncio
    async def test_bad_json_raises_device_exception(self):
        resp = _resp()
        resp.json = AsyncMock(side_effect=ValueError("bad json"))
        c, _, _ = _client(resp)
        with pytest.raises(DeviceException):
            await c.get("/gateway")


class TestPut:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("status", [200, 204])
    async def test_success_returns_true(self, status):
        c, session, _ = _client(_resp(status=status, body="", content_type=""))
        assert await c.put("/zones/zn1/manualTemperatureHeating", 21.5) is True
        kwargs = session.request.call_args.kwargs
        assert json.loads(kwargs["data"]) == {"value": 21.5}
        assert kwargs["headers"]["Content-Type"] == "application/json"

    @pytest.mark.asyncio
    async def test_401_raises_failed_auth(self):
        c, _, _ = _client(_resp(status=401))
        with pytest.raises(FailedAuthException):
            await c.put("/path", "value")

    @pytest.mark.asyncio
    async def test_500_raises_device_exception(self):
        c, _, _ = _client(_resp(status=500, body="err", content_type="text/plain"))
        with pytest.raises(DeviceException, match="500"):
            await c.put("/path", "value")


def _envelope(paths, server_status=200, gw_status=200):
    return [
        {
            "gatewayId": "123",
            "resourcePaths": [
                {
                    "resourcePath": p,
                    "serverStatus": server_status,
                    "gatewayResponse": {
                        "status": gw_status,
                        "payload": {"id": p, "value": f"v-{p}"},
                    },
                }
                for p in paths
            ],
        }
    ]


class TestBulk:
    @pytest.mark.asyncio
    async def test_45_paths_go_out_in_two_posts_with_one_token(self):
        paths = [f"/p/{i}" for i in range(45)]
        c, session, token_callback = _client(
            _resp(body=_envelope(paths[:30])), _resp(body=_envelope(paths[30:]))
        )
        result = await c.bulk(paths)
        assert session.request.call_count == 2
        assert len(result) == 45
        assert result["/p/44"]["value"] == "v-/p/44"
        token_callback.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_body_holds_gateway_id_and_paths(self):
        c, session, _ = _client(_resp(body=_envelope(["/a"])))
        await c.bulk(["/a"])
        method, url = session.request.call_args.args
        assert (method, url) == ("POST", POINTTAPI_BULK_URL)
        body = json.loads(session.request.call_args.kwargs["data"])
        assert body == [{"gatewayId": "123", "resourcePaths": ["/a"]}]

    @pytest.mark.asyncio
    async def test_failed_paths_inside_a_200_are_left_out(self):
        envelope = _envelope(["/ok"])
        envelope[0]["resourcePaths"] += [
            {
                "resourcePath": "/forbidden",
                "serverStatus": 403,
                "gatewayResponse": None,
            },
            {
                "resourcePath": "/broken",
                "serverStatus": 200,
                "gatewayResponse": {"status": 500, "payload": None},
            },
        ]
        c, _, _ = _client(_resp(body=envelope))
        assert list(await c.bulk(["/ok", "/forbidden", "/broken"])) == ["/ok"]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("envelope", [{"not": "a list"}, [], "text"])
    async def test_unreadable_envelope_raises_device_exception(self, envelope):
        c, _, _ = _client(_resp(body=envelope))
        with pytest.raises(DeviceException, match="envelope"):
            await c.bulk(["/a"])

    @pytest.mark.asyncio
    async def test_401_raises_failed_auth(self):
        c, _, _ = _client(_resp(status=401))
        with pytest.raises(FailedAuthException):
            await c.bulk(["/a"])

    @pytest.mark.asyncio
    async def test_500_raises_device_exception(self):
        c, _, _ = _client(_resp(status=500, body={}))
        with pytest.raises(DeviceException, match="500"):
            await c.bulk(["/a"])


class TestListGateways:
    @pytest.mark.asyncio
    async def test_returns_gateway_list(self):
        gateways = [{"deviceId": "101506113", "deviceType": "rrc2"}]
        c, session, _ = _client(_resp(body=gateways))
        assert await c.list_gateways() == gateways
        assert session.request.call_args.args == ("GET", POINTTAPI_BASE_URL)

    @pytest.mark.asyncio
    async def test_401_raises_failed_auth(self):
        c, _, _ = _client(_resp(status=401))
        with pytest.raises(FailedAuthException):
            await c.list_gateways()

    @pytest.mark.asyncio
    async def test_non_list_payload_raises_device_exception(self):
        c, _, _ = _client(_resp(body={"unexpected": "shape"}))
        with pytest.raises(DeviceException, match="shape"):
            await c.list_gateways()
