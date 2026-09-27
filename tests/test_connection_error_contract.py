"""An unreachable gateway must be visible on every polled object.

`DeviceConnectionError` is the signal a consumer turns into "entity
unavailable". If some object types swallow it, a gateway that is completely
unreachable still reports success for those, and the consumer cannot tell.

These tests walk the object graph by `update()` implementation rather than by
class name, so a new class inheriting one of these `update()`s is covered
automatically.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bosch_thermostat_client.circuits.circuit import BasicCircuit, Circuit
from bosch_thermostat_client.const import ID, NAME, PATH, RESULT, TYPE, URI, REGULAR
from bosch_thermostat_client.exceptions import (
    DeviceConnectionError,
    DeviceException,
    MsgConnectionError,
    MsgException,
)
from bosch_thermostat_client.helper import BoschSingleEntity
from bosch_thermostat_client.sensors.sensor import Sensor
from bosch_thermostat_client.switches.boolean import BinarySwitch
from bosch_thermostat_client.switches.number import NumberSwitch
from bosch_thermostat_client.switches.select import SelectSwitch
from bosch_thermostat_client.switches.switch import Switch

_PATCH_TARGET = "bosch_thermostat_client.connectors.xmpp.BoschClientXMPP"


# ---------------------------------------------------------------------------
# The exception hierarchy the contract rests on
# ---------------------------------------------------------------------------


def test_connection_errors_are_device_exceptions():
    """Existing `except DeviceException` handlers must keep working."""
    assert issubclass(DeviceConnectionError, DeviceException)
    assert issubclass(MsgConnectionError, DeviceConnectionError)
    assert issubclass(MsgConnectionError, MsgException)


# ---------------------------------------------------------------------------
# Every update() implementation that polls the connector
# ---------------------------------------------------------------------------


def _sensor():
    sensor = Sensor(
        attr_id="sensor1",
        path="/sensor1",
        connector=AsyncMock(),
        name="sensor1",
    )
    return sensor


def _switch(cls, **kwargs):
    switch = cls(
        attr_id="switch1",
        path="/switch1",
        connector=AsyncMock(),
        name="switch1",
        result={},
        **kwargs,
    )
    return switch


def _circuit():
    circuit = Circuit.__new__(Circuit)
    circuit._connector = AsyncMock()
    circuit._state = False
    circuit._omit_updates = []
    circuit._main_data = {NAME: "hc1", ID: "/hc1", PATH: None}
    circuit._data = {"temp": {URI: "/hc1/currentTemp", TYPE: "temperature", RESULT: {}}}
    return circuit


def _basic_circuit():
    circuit = BasicCircuit.__new__(BasicCircuit)
    circuit._connector = AsyncMock()
    circuit._state = True
    circuit._data = {"status": {URI: "/hc1/status", TYPE: REGULAR, RESULT: {}}}
    return circuit


ALL_POLLED = {
    "Sensor": _sensor,
    "Switch": lambda: _switch(Switch),
    "BinarySwitch": lambda: _switch(BinarySwitch),
    "SelectSwitch": lambda: _switch(SelectSwitch),
    "NumberSwitch": lambda: _switch(NumberSwitch, default_step=1),
    "Circuit": _circuit,
}


@pytest.mark.parametrize("name", sorted(ALL_POLLED))
@pytest.mark.asyncio
async def test_update_reraises_connection_error(name):
    """No polled object may report success when the gateway is unreachable."""
    obj = ALL_POLLED[name]()
    obj._connector.get.side_effect = DeviceConnectionError("Connection timed out")

    with pytest.raises(DeviceConnectionError):
        await obj.update()

    assert obj._state is False, f"{name} reported success on an unreachable gateway"


@pytest.mark.parametrize("name", sorted(ALL_POLLED))
@pytest.mark.asyncio
async def test_update_still_swallows_ordinary_device_exception(name):
    """A missing endpoint is not an unreachable gateway; keep absorbing it."""
    obj = ALL_POLLED[name]()
    obj._connector.get.side_effect = DeviceException("URI doesn not exist: 404")

    await obj.update()  # must not raise


@pytest.mark.asyncio
async def test_switches_share_one_update_implementation():
    """Guards the coverage claim: all four switch types use the same update().

    If a switch class ever grows its own update(), this fails and the new one
    needs the same DeviceConnectionError rule.
    """
    for cls in (Switch, BinarySwitch, SelectSwitch, NumberSwitch):
        assert cls.update is BoschSingleEntity.update, (
            f"{cls.__name__} overrides update(); it needs its own "
            "DeviceConnectionError handling"
        )


@pytest.mark.asyncio
async def test_update_requested_key_reraises_without_strict_flag():
    """BasicCircuit.initialize() passes strict_connection; polling does not.

    Discovery must fail loudly either way once the transport says unreachable.
    """
    circuit = _basic_circuit()
    circuit._connector.get.side_effect = DeviceConnectionError("Connection timed out")

    with pytest.raises(DeviceConnectionError):
        await circuit.update_requested_key("status", strict_connection=True)


# ---------------------------------------------------------------------------
# The XMPP transport has to produce the signal in the first place
# ---------------------------------------------------------------------------


def _xmpp_connector():
    from bosch_thermostat_client.connectors.ivt import IVTXMPPConnector

    client = MagicMock()
    client.plugin = {}
    with patch(_PATCH_TARGET, return_value=client):
        connector = IVTXMPPConnector(
            host="SERIAL", encryption=MagicMock(), access_key="ACCESSKEY"
        )
    return connector, client


@pytest.mark.asyncio
async def test_xmpp_connect_timeout_is_a_connection_error():
    connector, client = _xmpp_connector()
    client.is_connected.return_value = False
    connector._auth_success = False

    with patch("bosch_thermostat_client.connectors.xmpp.TIMEOUT", 0.01):
        with pytest.raises(DeviceConnectionError):
            await connector._request(method="get", path="/gateway/uuid")


@pytest.mark.asyncio
async def test_xmpp_request_timeout_is_a_connection_error():
    connector, client = _xmpp_connector()
    connector._auth_success = True

    with patch("bosch_thermostat_client.connectors.xmpp.REQUEST_TIMEOUT", 0.01):
        with pytest.raises(MsgConnectionError):
            await connector._request(method="get", path="/gateway/uuid")


@pytest.mark.asyncio
async def test_xmpp_get_timeout_survives_the_retry():
    """get() retries twice; the type must not be flattened to DeviceException."""
    connector, client = _xmpp_connector()
    connector._auth_success = True

    with patch("bosch_thermostat_client.connectors.xmpp.REQUEST_TIMEOUT", 0.01):
        with pytest.raises(DeviceConnectionError):
            await connector.get("/gateway/uuid")

    assert client.send_message.call_count == 2


@pytest.mark.asyncio
async def test_session_end_fails_pending_as_connection_error():
    """A dropped session is a transport failure, not a gateway answer."""
    connector, _ = _xmpp_connector()
    from bosch_thermostat_client.connectors.xmpp import _PendingRequest

    future = asyncio.get_running_loop().create_future()
    connector._pending = {
        1: _PendingRequest(future=future, method="get", path="/gateway/uuid")
    }

    await connector.session_end()

    with pytest.raises(DeviceConnectionError):
        await future


@pytest.mark.asyncio
async def test_gateway_4xx_is_not_a_connection_error():
    """The device answered. That is not 'unreachable'."""
    connector, _ = _xmpp_connector()
    from bosch_thermostat_client.connectors.xmpp import _PendingRequest

    future = asyncio.get_running_loop().create_future()
    connector._pending = {
        2: _PendingRequest(future=future, method="get", path="/gateway/uuid")
    }

    connector.main_listener(
        {"type": "chat", "body": "HTTP/1.0 400 Bad Request\r\rSeq-No: 2\r\r"}
    )

    with pytest.raises(MsgException) as caught:
        await future
    assert not isinstance(caught.value, DeviceConnectionError)
