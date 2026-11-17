"""Tests for Sensor metadata (device_class, state_class, and unitOfMeasure fallback).

Verifies that:
- Sensor captures unitOfMeasure, device_class, and state_class from schema definitions
- Sensor.unit_of_measurement property returns the configured or live unit
- Fallback unitOfMeasure is preserved when gateway update omits unitOfMeasure
- Gateway-provided unitOfMeasure overrides schema fallback
- RC300/RC200 database schemas correctly define metadata for supply_t1, return, systemPressure, etc.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from bosch_thermostat_client.const import RESULT, UNITS, VALUE
from bosch_thermostat_client.sensors.sensor import Sensor

DB_DIR = Path(__file__).resolve().parents[1] / "bosch_thermostat_client" / "db"


def _make_sensor(
    attr_id="supply_t1",
    path="/system/sensors/temperatures/supply_t1",
    unit_of_measure="C",
    device_class="temperature",
    state_class="measurement",
    connector=None,
):
    """Construct a Sensor with schema metadata."""
    if connector is None:
        connector = AsyncMock()
    return Sensor(
        connector=connector,
        attr_id=attr_id,
        name="Actual supply temp",
        path=path,
        device_class=device_class,
        state_class=state_class,
        unitOfMeasure=unit_of_measure,
    )


def test_sensor_initializes_with_schema_unit_and_classes():
    """Sensor must retain unitOfMeasure, device_class, and state_class upon init."""
    sensor = _make_sensor()
    assert sensor.device_class == "temperature"
    assert sensor.state_class == "measurement"
    assert sensor.unit_of_measurement == "C"
    assert sensor.get_property(sensor.attr_id).get(UNITS) == "C"


def test_sensor_update_preserves_schema_unit_when_gateway_omits_unit():
    """When gateway returns value without unitOfMeasure, schema fallback must be preserved."""
    sensor = _make_sensor()
    # Simulate gateway response with no unitOfMeasure (typical for supply_t1)
    sensor.process_results({VALUE: 45.2}, key=sensor.attr_id)

    assert sensor.state == 45.2
    assert sensor.unit_of_measurement == "C"
    assert sensor.get_property(sensor.attr_id).get(UNITS) == "C"


def test_sensor_update_preserves_schema_unit_when_gateway_returns_empty_unit():
    """When gateway returns empty string for unitOfMeasure, fallback unit is preserved."""
    sensor = _make_sensor()
    sensor.process_results({VALUE: 42.0, UNITS: ""}, key=sensor.attr_id)

    assert sensor.state == 42.0
    assert sensor.unit_of_measurement == "C"
    assert sensor.get_property(sensor.attr_id).get(UNITS) == "C"


def test_sensor_update_overrides_schema_unit_when_gateway_provides_unit():
    """Gateway-provided unitOfMeasure must take precedence when present."""
    sensor = _make_sensor(unit_of_measure="C")
    sensor.process_results({VALUE: 113.4, UNITS: "F"}, key=sensor.attr_id)

    assert sensor.state == 113.4
    assert sensor.unit_of_measurement == "F"
    assert sensor.get_property(sensor.attr_id).get(UNITS) == "F"


def test_rc300_database_sensors_metadata():
    """Verify that rc300_rc200 schema files contain metadata for critical sensors."""
    schema_path = DB_DIR / "rc300_rc200" / "040803.json"
    schema = json.loads(schema_path.read_text())
    sensors = schema["sensors"]

    # Temperatures
    for temp_sensor in ["supply_t1", "supply_t1_setpoint", "return", "switch_temperature"]:
        assert temp_sensor in sensors
        entry = sensors[temp_sensor]
        assert entry.get("device_class") == "temperature", f"{temp_sensor} missing device_class"
        assert entry.get("state_class") == "measurement", f"{temp_sensor} missing state_class"
        assert entry.get("unitOfMeasure") == "C", f"{temp_sensor} missing unitOfMeasure"

    # Pressure
    assert "systemPressure" in sensors
    pressure = sensors["systemPressure"]
    assert pressure.get("device_class") == "pressure"
    assert pressure.get("state_class") == "measurement"
    assert pressure.get("unitOfMeasure") == "bar"

    # Power
    assert "actualPower" in sensors
    power = sensors["actualPower"]
    assert power.get("device_class") == "power"
    assert power.get("state_class") == "measurement"
    assert power.get("unitOfMeasure") == "kW"

    # Modulation
    assert "actualModulation" in sensors
    mod = sensors["actualModulation"]
    assert mod.get("state_class") == "measurement"
    assert mod.get("unitOfMeasure") == "%"
