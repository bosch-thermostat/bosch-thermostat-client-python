"""Tests for repeated update error logging."""

import logging

from bosch_thermostat_client.exceptions import DeviceException
from bosch_thermostat_client.sensors.sensor import (
    MISSING_ENDPOINT_WARNING_INTERVAL,
    Sensor,
)


def _sensor():
    return Sensor(
        attr_id="suWiThreshold",
        path="/heatingCircuits/hc1/suWiThreshold",
        name="Summer Winter Threshold",
        connector=None,
    )


def test_missing_endpoint_errors_are_throttled_but_rechecked(caplog):
    entity = _sensor()
    error = DeviceException(
        "URI /heatingCircuits/hc1/suWiThreshold doesn not exist: 404"
    )

    with caplog.at_level(logging.DEBUG):
        for _ in range(MISSING_ENDPOINT_WARNING_INTERVAL + 1):
            entity._log_sensor_update_error(
                "/heatingCircuits/hc1/suWiThreshold",
                error,
            )

    warning_messages = [
        record.message for record in caplog.records if record.levelno == logging.WARNING
    ]

    assert len(warning_messages) == 2
    assert "Summer Winter Threshold" in warning_messages[0]
    assert "suWiThreshold" in warning_messages[0]


def test_non_404_errors_are_not_throttled(caplog):
    entity = _sensor()
    error = DeviceException("Connection timed out for /heatingCircuits/hc1/suWiThreshold")

    with caplog.at_level(logging.DEBUG):
        for _ in range(3):
            entity._log_sensor_update_error(
                "/heatingCircuits/hc1/suWiThreshold",
                error,
            )

    warning_messages = [
        record.message for record in caplog.records if record.levelno == logging.WARNING
    ]

    assert len(warning_messages) == 3
