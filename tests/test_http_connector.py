import asyncio
import pytest
from unittest.mock import MagicMock
from aiohttp import ClientSession
from bosch_thermostat_client.connectors import HttpConnector
from bosch_thermostat_client.errors import Response404Error, RequestError, ResponseError
from .gateway_test_server import GatewayTestServer

TIMEOUT = 2


@pytest.mark.asyncio
async def test_request_complete():
    async with GatewayTestServer() as server:
        async with ClientSession() as session:
            loop = asyncio.get_event_loop()
            gtw_host = str(server.host) + ":" + str(server.port)
            encryption = MagicMock()
            encryption.json_decrypt = lambda x: x # pass-through for test
            httpConnector = HttpConnector(gtw_host, encryption, loop=session)
            task = loop.create_task(httpConnector.request("/gateway/uuid"))
            request = await server.receive_request()
            assert request.path_qs == "/gateway/uuid"
            server.send_response(
                request, text='{"id":"/gateway/uuid"}', content_type="application/json"
            )
            response = await task
            assert '{"id":"/gateway/uuid"}' == response


@pytest.mark.asyncio
async def test_request_notfound():
    async with GatewayTestServer() as server:
        async with ClientSession() as session:
            loop = asyncio.get_event_loop()
            gtw_host = str(server.host) + ":" + str(server.port)
            encryption = MagicMock()
            httpConnector = HttpConnector(gtw_host, encryption, loop=session)
            task = loop.create_task(httpConnector.request("/blablabla"))
            request = await server.receive_request()
            assert request.path_qs == "/blablabla"
            server.send_response(request, status=404)
            with pytest.raises(Response404Error):
                await task


@pytest.mark.asyncio
async def test_request_connection_failure(unused_tcp_port):
    async with GatewayTestServer() as server:
        async with ClientSession() as session:
            gtw_host = "127.0.0.1:" + str(unused_tcp_port)
            encryption = MagicMock()
            httpConnector = HttpConnector(gtw_host, encryption, loop=session)
            # Use a short timeout to avoid hanging if it doesn't fail fast
            with pytest.raises(DeviceException): # Connector raises DeviceException on connection failure
                await asyncio.wait_for(httpConnector.request("/blablabla"), TIMEOUT)


@pytest.mark.asyncio
async def test_request_forbidden():
    async with GatewayTestServer() as server:
        async with ClientSession() as session:
            loop = asyncio.get_event_loop()
            gtw_host = str(server.host) + ":" + str(server.port)
            encryption = MagicMock()
            httpConnector = HttpConnector(gtw_host, encryption, loop=session)
            task = loop.create_task(httpConnector.request("/blablabla"))
            request = await server.receive_request()
            assert request.path_qs == "/blablabla"
            server.send_response(request, status=403)
            with pytest.raises(DeviceException): # Connector wraps ResponseException in DeviceException
                await task

from bosch_thermostat_client.exceptions import DeviceException
