"""Verification of exception logging for suppressed errors.

Ensures that expected exceptions occurring in background tasks or 
recovery paths are correctly emitted to the DEBUG log rather than
being silently swallowed.
"""
import asyncio
from unittest.mock import AsyncMock, patch
from datetime import datetime, timedelta

import pytest


# ---------------------------------------------------------------------------
# Site 1: circuit.py BasicCircuit.update_requested_key — DeviceException
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_update_requested_key_debug_logged_on_device_exception():
    """Verify that DeviceException in update_requested_key is logged at DEBUG level."""
    from bosch_thermostat_client.circuits.circuit import BasicCircuit
    from bosch_thermostat_client.exceptions import DeviceException

    mock_connector = AsyncMock()
    mock_connector.get.side_effect = DeviceException("test error")

    circuit = BasicCircuit.__new__(BasicCircuit)
    circuit._connector = mock_connector
    circuit._state = True
    circuit._data = {"STATUS": {"uri": "/test/status", "URI": "/test/status"}}

    with patch("bosch_thermostat_client.circuits.circuit._LOGGER") as mock_log:
        await circuit.update_requested_key("STATUS")
        assert mock_log.debug.called


# ---------------------------------------------------------------------------
# Site 2: circuit.py Circuit.update() fetch_data — DeviceException
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_circuit_update_fetch_data_debug_logged_on_device_exception():
    """Verify that DeviceException during Circuit.update data fetching is logged at DEBUG level."""
    from bosch_thermostat_client.circuits.circuit import Circuit
    from bosch_thermostat_client.exceptions import DeviceException
    from bosch_thermostat_client.const import URI, TYPE, RESULT, NAME, ID, PATH

    mock_connector = AsyncMock()
    mock_connector.get.side_effect = DeviceException("fetch error")

    circuit = Circuit.__new__(Circuit)
    circuit._connector = mock_connector
    circuit._state = False
    circuit._omit_updates = []
    circuit._main_data = {NAME: "hc1", ID: "/hc1", PATH: None}
    circuit._data = {
        "temp": {URI: "/hc1/currentTemp", TYPE: "temperature", RESULT: {}}
    }

    with patch("bosch_thermostat_client.circuits.circuit._LOGGER") as mock_log:
        await circuit.update()
        # Ensure at least one debug message was emitted related to the failure
        assert any("fetch error" in str(arg) or "Exception" in str(arg) 
                  for call in mock_log.debug.call_args_list for arg in call.args)


# ---------------------------------------------------------------------------
# Site 3: energy.py fetch_range outer ValueError (days_to_find.remove)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fetch_range_outer_valueerror_debug_logged():
    """Verify that suppressed ValueError in fetch_range is logged at DEBUG level."""
    from bosch_thermostat_client.sensors.energy import EnergySensor

    connector = AsyncMock()
    sensor = EnergySensor(
        attr_id="energySensor",
        path="/energy/test",
        connector=connector,
        name="energy_test",
        pagination="/energy/pagination",
    )
    sensor._page_number = 3

    yesterday = datetime.today() - timedelta(days=1)
    day_str = yesterday.strftime("%d-%m-%Y")
    sensor._past_data = {day_str: {"d": day_str, "val": 1}}

    with patch("bosch_thermostat_client.sensors.energy._LOGGER") as mock_log:
        await sensor.fetch_range(yesterday, yesterday)
        assert mock_log.debug.called


# ---------------------------------------------------------------------------
# Site 4: energy.py fetch_range inner ValueError (row["d"] remove)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fetch_range_inner_valueerror_debug_logged():
    """Verify that suppressed ValueError during row processing in fetch_range is logged at DEBUG level."""
    from bosch_thermostat_client.sensors.energy import EnergySensor

    connector = AsyncMock()
    sensor = EnergySensor(
        attr_id="energySensor",
        path="/energy/test",
        connector=connector,
        name="energy_test",
        pagination="/energy/pagination",
    )
    sensor._page_number = 2

    yesterday = datetime.today() - timedelta(days=1)
    two_days_ago = datetime.today() - timedelta(days=2)

    unrelated_day = (datetime.today() - timedelta(days=30)).strftime("%d-%m-%Y")
    connector.get.return_value = {"value": [{"d": unrelated_day}]}

    with patch("bosch_thermostat_client.sensors.energy._LOGGER") as mock_log:
        await sensor.fetch_range(two_days_ago, yesterday)
        assert mock_log.debug.called


# ---------------------------------------------------------------------------
# Site 5: energy.py update() DeviceException from pagination get
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_energy_update_deviceexception_debug_logged():
    """Verify that DeviceException during pagination fetch in update is logged at DEBUG level."""
    from bosch_thermostat_client.sensors.energy import EnergySensor
    from bosch_thermostat_client.exceptions import DeviceException

    connector = AsyncMock()
    connector.get.side_effect = DeviceException("pagination unavailable")

    sensor = EnergySensor(
        attr_id="energySensor",
        path="/energy/test",
        connector=connector,
        name="energy_test",
        pagination="/energy/pagination",
    )
    sensor._page_number = None

    with patch("bosch_thermostat_client.sensors.energy._LOGGER") as mock_log:
        await sensor.update(time=datetime.today())
        assert mock_log.debug.called


# ---------------------------------------------------------------------------
# Site 6: connectors/xmpp.py asyncio.InvalidStateError → should be .debug
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_xmpp_already_completed_seq_no_logged_at_debug():
    """Verify that responses for already completed futures are logged at DEBUG."""
    from bosch_thermostat_client.connectors.xmpp import XMPPBaseConnector
    from unittest.mock import MagicMock

    connector = XMPPBaseConnector.__new__(XMPPBaseConnector)
    
    # Simulate an already-resolved future
    mock_future = MagicMock()
    mock_future.done.return_value = True
    
    connector._pending = {1: mock_future}
    connector._encryption = MagicMock()
    
    # Simple dict-like object for msg
    msg = {"type": "chat", "body": "HTTP/1.1 200 OK\nSeq-No: 1\n\nbody"}

    with patch("bosch_thermostat_client.connectors.xmpp._LOGGER") as mock_log:
        connector.main_listener(msg)
        # Should log about 'already completed Seq-No' at debug level
        # Line 292: "Received XMPP response for unknown or already completed Seq-No: %d"
        assert any("already completed Seq-No" in str(arg) 
                  for call in mock_log.debug.call_args_list for arg in call.args)
