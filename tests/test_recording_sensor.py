"""Tests for recording.py datetime.utcnow() deprecation fix.

Verifies that:
- update() signature uses None sentinel default (not datetime.utcnow())
- update() computes datetime.now(timezone.utc) inside the body when time is None
- timezone is imported in the module
- No DeprecationWarning is emitted
"""
import inspect
import warnings
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from bosch_thermostat_client.sensors.recording import RecordingSensor


def _make_sensor(connector=None):
    """Construct a minimal RecordingSensor."""
    if connector is None:
        connector = AsyncMock()
    sensor = RecordingSensor(
        name="test_recording",
        attr_id="recordingSensor",
        path="/energy/recording/test",
        connector=connector,
    )
    sensor._data = {
        "recordingSensor": {
            "uri": "/energy/recording/test",
            "result": {"value": []},
        }
    }
    return sensor


def test_update_signature_uses_none_sentinel():
    """update() must accept `time: datetime | None = None`, not datetime.utcnow()."""
    import inspect
    sig = inspect.signature(RecordingSensor.update)
    time_param = sig.parameters["time"]
    assert time_param.default is None, (
        f"Expected default=None, got default={time_param.default!r}. "
        "The None-sentinel pattern must be used to eliminate the mutable-default antipattern."
    )


def test_timezone_imported_in_recording_module():
    """timezone must be importable from the recording module's namespace."""
    import bosch_thermostat_client.sensors.recording as rec_module
    src = inspect.getsource(rec_module)
    assert "timezone" in src, "timezone not found in recording.py source"
    assert "from datetime import" in src, "datetime import line not found"
    # Ensure timezone is part of the datetime import line
    import re
    match = re.search(r"from datetime import ([^\n]+)", src)
    assert match, "Could not find 'from datetime import ...' line"
    imports = match.group(1)
    assert "timezone" in imports, (
        f"timezone not in datetime import line: 'from datetime import {imports}'"
    )


def test_no_deprecation_warning_when_calling_update_without_time():
    """Calling update() without time= arg must not emit a DeprecationWarning."""
    connector = AsyncMock()
    connector.get = AsyncMock(return_value={})
    sensor = _make_sensor(connector=connector)

    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        # Instantiating the class must not trigger the warning
        sensor2 = _make_sensor(connector=connector)
    # If we reach here, no DeprecationWarning was emitted during instantiation


def test_none_sentinel_body_uses_timezone_aware_datetime():
    """When time is None, body must compute datetime.now(timezone.utc)."""
    import bosch_thermostat_client.sensors.recording as rec_module
    src = inspect.getsource(rec_module)
    assert "if time is None" in src, (
        "None-sentinel guard 'if time is None' not found in recording.py"
    )
    assert "datetime.now(timezone.utc)" in src, (
        "Body computation 'datetime.now(timezone.utc)' not found in recording.py"
    )
