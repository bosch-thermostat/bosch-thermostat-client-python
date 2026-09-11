"""Schedule timestamp parsing tests."""
from types import SimpleNamespace

import pytest

from bosch_thermostat_client.const import ABSOLUTE
from bosch_thermostat_client.const.ivt import CAN
from bosch_thermostat_client.schedule import Schedule

CT200_DATE_FORMAT = "%Y-%m-%dT%H:%M:%S%z"


def make_schedule(date_format=CT200_DATE_FORMAT):
    """Create a CT200 schedule with distinct Sunday and Monday values."""
    schedule = Schedule(
        connector=None,
        circuit_type="dhwCircuits",
        circuit_name="dhw1",
        current_time=None,
        bus_type=CAN,
        db={
            "schedule": {
                "program": "/dhwCircuits/{}/programs/{}/week",
                "key_day": "d",
                "key_setpoint": "dhw",
                "key_time": "t",
                "switch_points": "value",
            },
            "refs": {},
        },
        op_mode=SimpleNamespace(),
        date_format=date_format,
    )
    schedule._switchprogram_mode = ABSOLUTE
    schedule._switch_points = [
        {"d": "Su", "dhw": "17.0", "t": 1380},
        {"d": "Mo", "dhw": "21.0", "t": 0},
    ]
    return schedule


def test_ct200_naive_timestamp_uses_device_local_weekday():
    schedule = make_schedule()
    schedule._time = "2026-08-24T00:30:00"

    assert schedule.get_temp_in_schedule()["temp"] == 21.0


@pytest.mark.parametrize(
    "timestamp",
    ["2026-08-24T00:30:00+02:00", "2026-08-24T00:30:00Z"],
)
def test_ct200_offset_timestamps_keep_existing_behavior(timestamp):
    schedule = make_schedule()
    schedule._time = timestamp

    assert schedule.get_temp_in_schedule()["temp"] == 21.0


def test_non_ct200_date_format_keeps_existing_parser():
    schedule = make_schedule("%Y-%m-%dT%H:%M:%S")
    schedule._time = "2026-08-24T00:30:00"

    assert schedule.get_temp_in_schedule()["temp"] == 21.0


@pytest.mark.parametrize(
    "timestamp",
    [
        "not-a-date",
        "2026-08-24 00:30:00",
        "2026-8-24T00:30:00",
        "2026-02-30T00:30:00",
        "2026-08-24T00:30:00+invalid",
    ],
)
def test_malformed_ct200_timestamp_still_raises_value_error(timestamp):
    schedule = make_schedule()
    schedule._time = timestamp

    with pytest.raises(ValueError):
        schedule.get_temp_in_schedule()


def test_non_ct200_format_does_not_accept_ct200_naive_timestamp():
    schedule = make_schedule("%Y-%m-%d")
    schedule._time = "2026-08-24T00:30:00"

    with pytest.raises(ValueError):
        schedule.get_temp_in_schedule()
