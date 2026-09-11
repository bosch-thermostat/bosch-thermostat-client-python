"""HTTP connector class to Bosch thermostat."""
import logging
import asyncio
import json
from asyncio import TimeoutError as AsyncTimeout
from aiohttp.client_exceptions import (
    ClientResponseError,
    ClientConnectionError,
    ClientError,
)

from bosch_thermostat_client.const.ivt import HTTP_HEADER, IVT
from bosch_thermostat_client.const import APP_JSON, GET, PUT
from bosch_thermostat_client.exceptions import (
    DeviceConnectionError, DeviceException, ResponseException,
)

_LOGGER = logging.getLogger(__name__)


class HttpConnector:
    """HTTP connector to Bosch thermostat."""

    def __init__(self, host, encryption, device_type=IVT, **kwargs):
        """Init of HTTP connector."""
        self._lock = asyncio.Lock()
        self._host = host
        self._websession = kwargs.get("loop")
        self._request_timeout = 10
        self._encryption = encryption
        self.device_type = device_type

    @property
    def encryption_key(self):
        return self._encryption.key

    async def _request(self, method, path, **kwargs):
        _LOGGER.debug("Sending %s request to %s", method.__name__.upper(), path)

        async def get_response(method_name, res):
            if method_name == PUT:
                data = await res.text()
                if not data and res.status == 204:
                    return True
                return data
            if (
                method_name == GET
                and res.status == 200
                and res.content_type == APP_JSON
            ):
                data = await res.json(loads=self._encryption.json_decrypt)
                return data
            raise ResponseException(res)

        try:
            async with method(self._format_url(path), **kwargs) as res:
                return await get_response(method.__name__, res)
        except ClientResponseError as err:
            raise DeviceException(f"URI {path} doesn not exist: {err}")
        except ClientConnectionError as err:
            raise DeviceConnectionError(err) from err
        except ResponseException as err:
            raise DeviceException(f"Error requesting data from {path}: {err}")
        except ClientError as err:
            raise DeviceException(f"Error connecting to client {path}: {err}")
        except AsyncTimeout as err:
            raise DeviceConnectionError(f"Connection timed out for {path}.") from err

    def _format_url(self, path):
        """Format URL to make requests to gateway."""
        return f"http://{self._host}{path}"

    def set_timeout(self, timeout=10):
        """Set timeout for API calls."""
        self._request_timeout = timeout

    async def get(self, path):
        """Get message from API with given path."""
        async with self._lock:
            data = await self._request(
                self._websession.get,
                path,
                headers=HTTP_HEADER,
                timeout=self._request_timeout,
                skip_auto_headers=["Accept-Encoding", "Accept"],
                raise_for_status=True,
            )
            _LOGGER.debug("Response to GET request %s: %s", path, json.dumps(data))
            return data

    async def put(self, path, value):
        """Send message to API with given path."""
        async with self._lock:
            return await self._request(
                self._websession.put,
                path,
                data=self._encryption.encrypt(json.dumps({"value": value})),
                headers=HTTP_HEADER,
                timeout=self._request_timeout,
            )

    async def close(self, force=False):
        if force:
            await self._websession.close()
