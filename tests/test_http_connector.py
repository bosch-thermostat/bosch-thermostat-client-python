import asyncio
import pytest

pytest.skip(
    "Written against HttpConnector(host, session).request(path); the connector now "
    "takes (host, encryption, device_type) and exposes get()/put(). The GatewayTestServer "
    "harness it uses is fixed and working, so this is the first suite worth restoring.",
    allow_module_level=True,
)
from aiohttp import ClientSession  # noqa: E402
from bosch_thermostat_client.connectors import HttpConnector  # noqa: E402
from bosch_thermostat_client.errors import Response404Error, RequestError, ResponseError  # noqa: E402
from .gateway_test_server import GatewayTestServer  # noqa: E402

TIMEOUT = 1


@pytest.mark.asyncio
async def test_request_complete():
    async with GatewayTestServer() as server:
        async with ClientSession() as session:
            loop = asyncio.get_event_loop()
            gtw_host = str(server.host) + ":" + str(server.port)
            httpConnector = HttpConnector(gtw_host, session)
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
            httpConnector = HttpConnector(gtw_host, session)
            task = loop.create_task(httpConnector.request("/blablabla"))
            request = await server.receive_request()
            assert request.path_qs == "/blablabla"
            server.send_response(request, status=404)
            with pytest.raises(Response404Error):
                await task


@pytest.mark.asyncio
async def test_request_connection_failure(aiohttp_unused_port):
    async with GatewayTestServer() as server:
        async with ClientSession() as session:

            gtw_host = str(server.host) + ":" + str(aiohttp_unused_port)
            httpConnector = HttpConnector(gtw_host, session)
            with pytest.raises(RequestError):
                await asyncio.wait_for(httpConnector.request("/blablabla"), TIMEOUT)


@pytest.mark.asyncio
async def test_request_forbidden():
    async with GatewayTestServer() as server:
        async with ClientSession() as session:
            loop = asyncio.get_event_loop()
            gtw_host = str(server.host) + ":" + str(server.port)
            httpConnector = HttpConnector(gtw_host, session)
            task = loop.create_task(httpConnector.request("/blablabla"))
            request = await server.receive_request()
            assert request.path_qs == "/blablabla"
            server.send_response(request, status=403)
            with pytest.raises(ResponseError):
                await task
