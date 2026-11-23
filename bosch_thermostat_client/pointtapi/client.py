"""HTTP client for the Bosch POINTTAPI cloud JSON API (CT200, EasyControl).

Authentication failures (HTTP 401/403) raise FailedAuthException, so a
consumer can ask the user to log in again. Every other failure raises a
DeviceException: DeviceConnectionError when no response arrived.
"""

from __future__ import annotations

import json
import logging
from urllib.parse import urljoin

import aiohttp

from bosch_thermostat_client.exceptions import (
    DeviceConnectionError,
    DeviceException,
    FailedAuthException,
)

_LOGGER = logging.getLogger(__name__)

POINTTAPI_API_ROOT = "https://pointt-api.bosch-thermotechnology.com/pointt-api/api/v1/"
POINTTAPI_BASE_URL = f"{POINTTAPI_API_ROOT}gateways/"
POINTTAPI_BULK_URL = f"{POINTTAPI_API_ROOT}bulk"
APP_JSON = "application/json"
TIMEOUT = aiohttp.ClientTimeout(total=30)

# The bulk endpoint accepts at most 30 resource paths per request. Wire format
# first documented by serbanb11/homecom_alt, verified on a CT200 in June 2026.
MAX_BULK_PATHS = 30


async def _request(session, method: str, url: str, what: str, token: str, **kwargs):
    """Send one request; return (status, body).

    body is parsed JSON when the response says it is JSON, else text.
    """
    headers = {"Authorization": f"Bearer {token}"}
    if "data" in kwargs:
        headers["Content-Type"] = APP_JSON
    try:
        async with session.request(
            method, url, headers=headers, timeout=TIMEOUT, **kwargs
        ) as resp:
            if resp.status in (401, 403):
                _LOGGER.debug("POINTTAPI %s: HTTP %s", what, resp.status)
                raise FailedAuthException(f"POINTTAPI {what}: HTTP {resp.status}")
            if resp.content_type and APP_JSON in resp.content_type:
                body = await resp.json()
            else:
                body = await resp.text()
            return resp.status, body
    except (aiohttp.ClientConnectionError, TimeoutError) as err:
        raise DeviceConnectionError(f"POINTTAPI {what}: {err}") from err
    except (aiohttp.ClientError, ValueError) as err:
        raise DeviceException(f"POINTTAPI {what}: {err}") from err


async def async_list_gateways(session, token: str) -> list[dict]:
    """Return the account's gateways: [{"deviceId": ..., "deviceType": ...}].

    Module level, so a login flow can call it before a gateway is chosen.
    """
    status, data = await _request(
        session, "GET", POINTTAPI_BASE_URL, "gateway list", token
    )
    if status != 200:
        raise DeviceException(f"POINTTAPI gateway list failed: HTTP {status}")
    if not isinstance(data, list):
        raise DeviceException("POINTTAPI gateway list: unexpected payload shape")
    return data


class PoinTTAPIClient:
    """GET, PUT and bulk reads for one gateway, with a Bearer token."""

    def __init__(self, device_id: str, session, token_callback):
        """Initialize the client.

        device_id: gateway id (serial without dashes).
        session: aiohttp ClientSession, owned by the caller.
        token_callback: async callable returning a valid access token, for
            example PoinTTAPIAuth.async_get_access_token.
        """
        self._device_id = device_id
        self._session = session
        self._token_callback = token_callback
        self._base = f"{POINTTAPI_BASE_URL}{device_id}/resource/"

    @property
    def device_id(self) -> str:
        return self._device_id

    def _url(self, uri: str) -> str:
        return urljoin(self._base, uri.lstrip("/"))

    async def get(self, uri: str):
        """GET one resource path; returns parsed JSON, or text."""
        token = await self._token_callback()
        status, body = await _request(
            self._session, "GET", self._url(uri), f"GET {uri}", token
        )
        if status != 200:
            raise DeviceException(f"POINTTAPI GET {uri} failed: HTTP {status}")
        return body

    async def put(self, uri: str, value) -> bool:
        """PUT {"value": value} to one resource path."""
        token = await self._token_callback()
        status, body = await _request(
            self._session,
            "PUT",
            self._url(uri),
            f"PUT {uri}",
            token,
            data=json.dumps({"value": value}),
        )
        if status not in (200, 204):
            _LOGGER.debug(
                "POINTTAPI PUT %s HTTP %s body: %s", uri, status, str(body)[:500]
            )
            raise DeviceException(f"POINTTAPI PUT {uri} failed: HTTP {status}")
        return True

    async def bulk(self, paths: list[str]) -> dict:
        """Read many resource paths in bulk POSTs; returns {path: payload}.

        Paths use the same format as get() (leading slash, no /resource
        prefix: the bulk route refuses each path that has it). Requests go out
        one after another, MAX_BULK_PATHS paths each. A path that failed
        inside a 200 envelope is left out of the result. An envelope that
        cannot be read raises DeviceException, so callers can fall back to
        single GETs.
        """
        result: dict = {}
        token = await self._token_callback()
        for i in range(0, len(paths), MAX_BULK_PATHS):
            result.update(await self._bulk_single(paths[i : i + MAX_BULK_PATHS], token))
        return result

    async def _bulk_single(self, paths: list[str], token: str) -> dict:
        body = json.dumps(
            [{"gatewayId": self._device_id, "resourcePaths": list(paths)}]
        )
        status, envelope = await _request(
            self._session, "POST", POINTTAPI_BULK_URL, "bulk", token, data=body
        )
        if status != 200:
            raise DeviceException(f"POINTTAPI bulk failed: HTTP {status}")
        out: dict = {}
        try:
            for entry in envelope[0]["resourcePaths"]:
                path = entry["resourcePath"]
                if entry.get("serverStatus") != 200:
                    _LOGGER.debug(
                        "POINTTAPI bulk path %s serverStatus %s, skipping",
                        path,
                        entry.get("serverStatus"),
                    )
                    continue
                gw = entry.get("gatewayResponse") or {}
                if gw.get("status") != 200:
                    _LOGGER.debug(
                        "POINTTAPI bulk path %s gateway status %s, skipping",
                        path,
                        gw.get("status"),
                    )
                    continue
                out[path] = gw.get("payload")
        except (KeyError, IndexError, TypeError) as err:
            raise DeviceException(
                f"POINTTAPI bulk: unexpected envelope: {err}"
            ) from err
        return out

    async def list_gateways(self) -> list[dict]:
        """Return the account's gateways, like async_list_gateways."""
        return await async_list_gateways(self._session, await self._token_callback())
