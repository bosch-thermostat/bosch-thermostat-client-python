"""Transport failures must not look like missing gateway capabilities."""

import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from aiohttp import ClientResponseError, ServerDisconnectedError

from bosch_thermostat_client import exceptions
from bosch_thermostat_client.circuits.circuit import BasicCircuit
from bosch_thermostat_client.connectors.http import HttpConnector
from bosch_thermostat_client.const import HC
from bosch_thermostat_client.gateway.ivt import IVTGateway

# The fallback lets the regression tests execute against the unpatched client.
ConnectionFailure = getattr(
    exceptions, "DeviceConnectionError", exceptions.DeviceException
)


class FailingSession:
    def __init__(self, error):
        self.error = error
        self.calls = 0

    def get(self, *args, **kwargs):
        self.calls += 1
        raise self.error

    put = get


class StartupConnectionTests(unittest.IsolatedAsyncioTestCase):
    def gateway(self):
        return IVTGateway("HTTP", "gateway.invalid", "", access_key="00" * 32)

    async def test_timeout_keeps_type_and_cause(self):
        error = asyncio.TimeoutError()
        session = FailingSession(error)
        connector = HttpConnector("gateway.invalid", Mock(), loop=session)
        with self.assertRaises(exceptions.DeviceException) as caught:
            await connector.get("/system/info")
        self.assertEqual(type(caught.exception).__name__, "DeviceConnectionError")
        self.assertIs(caught.exception.__cause__, error)
        self.assertEqual(session.calls, 1)

    async def test_disconnect_keeps_type(self):
        connector = HttpConnector(
            "gateway.invalid", Mock(), loop=FailingSession(ServerDisconnectedError())
        )
        with self.assertRaises(exceptions.DeviceException) as caught:
            await connector.get("/system/info")
        self.assertEqual(type(caught.exception).__name__, "DeviceConnectionError")

    async def test_http_status_is_not_connection_failure(self):
        for status in (401, 404):
            session = FailingSession(
                ClientResponseError(
                    Mock(real_url="http://gateway.invalid/"), (), status=status
                )
            )
            connector = HttpConnector("gateway.invalid", Mock(), loop=session)
            with self.assertRaises(exceptions.DeviceException) as caught:
                await connector.get("/missing")
            self.assertEqual(type(caught.exception), exceptions.DeviceException)
            self.assertEqual(session.calls, 1)

    async def test_identity_failure_reaches_check_connection(self):
        gateway = self.gateway()
        error = ConnectionFailure("Connection timed out")
        gateway._connector.get = AsyncMock(side_effect=error)
        with self.assertRaises(ConnectionFailure) as caught:
            await gateway.check_connection()
        self.assertIs(caught.exception, error)
        self.assertEqual(gateway._connector.get.await_count, 1)

    async def test_firmware_timeout_is_not_unknown_firmware(self):
        gateway = self.gateway()
        error = ConnectionFailure("Connection timed out")

        async def get(path):
            if path == "/gateway/versionFirmware":
                raise error
            if path == "/system/info":
                return {"values": [{"Id": "158"}]}
            return {"value": "EMS"}

        gateway._connector.get = get
        with self.assertRaises(ConnectionFailure) as caught:
            await gateway.check_connection()
        self.assertIs(caught.exception, error)

    async def test_directory_failure_is_not_empty_circuits(self):
        gateway = self.gateway()
        gateway._db = {"heatingCircuits": {}}
        error = ConnectionFailure("Connection timed out")
        gateway._connector.get = AsyncMock(side_effect=error)
        with self.assertRaises(ConnectionFailure):
            await gateway.initialize_circuits(HC)

    async def test_child_directory_failure_is_not_empty_circuits(self):
        gateway = self.gateway()
        gateway._db = {"heatingCircuits": {}}
        gateway._connector.get = AsyncMock(
            side_effect=[
                {
                    "id": "/heatingCircuits",
                    "references": [{"id": "/heatingCircuits/hc1"}],
                },
                ConnectionFailure("Connection timed out"),
            ]
        )
        with self.assertRaises(ConnectionFailure):
            await gateway.initialize_circuits(HC)

    async def test_legitimate_empty_directory(self):
        gateway = self.gateway()
        gateway._db = {"heatingCircuits": {}}
        gateway._connector.get = AsyncMock(
            return_value={"id": "/heatingCircuits", "references": []}
        )
        self.assertEqual(await gateway.initialize_circuits(HC), [])

    async def test_missing_directory_remains_optional(self):
        gateway = self.gateway()
        gateway._db = {"heatingCircuits": {}}
        gateway._connector.get = AsyncMock(
            side_effect=exceptions.DeviceException("404")
        )
        self.assertEqual(await gateway.initialize_circuits(HC), [])

    async def test_circuit_status_failure_not_inactive(self):
        connector = SimpleNamespace(
            get=AsyncMock(side_effect=ConnectionFailure("Connection timed out"))
        )
        circuit = BasicCircuit(
            connector,
            "/heatingCircuits/hc1",
            {
                "heatingCircuits": {
                    "refs": {"status": {"id": "status", "type": "stringValue"}}
                },
            },
            "heatingCircuits",
            "EMS",
        )
        with self.assertRaises(ConnectionFailure):
            await circuit.initialize()

    async def test_cancellation_propagates(self):
        gateway = self.gateway()
        gateway._connector.get = AsyncMock(side_effect=asyncio.CancelledError())
        with self.assertRaises(asyncio.CancelledError):
            await gateway.check_connection()

    async def test_put_is_never_retried(self):
        session = FailingSession(asyncio.TimeoutError())
        connector = HttpConnector("gateway.invalid", Mock(), loop=session)
        with self.assertRaises(exceptions.DeviceException):
            await connector.put("/heatingCircuits/hc1/operationMode", "auto")
        self.assertEqual(session.calls, 1)


if __name__ == "__main__":
    unittest.main()
