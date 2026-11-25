"""A mode or a target an IVT gateway never gave is none, not off or 0 °C.

Measured on an iCom_low_CAN_v1 gateway on firmware 01.03.00: its second heating
circuit answers activeSwitchProgram with a value holding a control character, which
no JSON decoder accepts, and its hot water runs on Automatic, whose switch program
has no setpoint.
"""

import datetime

import pytest

from bosch_thermostat_client.circuits.circuits import choose_circuit_type
from bosch_thermostat_client.const import DHW, HC
from bosch_thermostat_client.const.ivt import CAN, IVT
from bosch_thermostat_client.db import get_db_of_firmware
from bosch_thermostat_client.exceptions import DeviceException


class Gateway:
    """Answers what it was given; anything else is a 404."""

    def __init__(self, answers):
        self.answers = answers
        self.device_type = IVT

    async def get(self, path, **kwargs):
        answer = self.answers.get(path)
        if answer is None:
            raise DeviceException(f"URI {path} doesn not exist: 404")
        if isinstance(answer, Exception):
            raise answer
        return answer


def value(path, value, allowed=None):
    answer = {"id": path, "type": "stringValue", "writeable": 1, "value": value}
    if allowed:
        answer["allowedValues"] = allowed
    return answer


def number(path, number, low=0.0, high=0.0):
    return {
        "id": path,
        "type": "floatValue",
        "writeable": 1,
        "value": number,
        "unitOfMeasure": "C",
        "minValue": low,
        "maxValue": high,
    }


PROGRAMS = ["HP_OPTIMIZED", "Program1", "Program2"]
UNDECODABLE = DeviceException("Unable to decode Json response.")


async def now():
    return datetime.datetime(2026, 11, 21, 17, 0)


async def circuit(kind, path, answers):
    database = await get_db_of_firmware(CAN, "01.03.00")
    Circuit = choose_circuit_type(IVT, kind)
    made = Circuit(
        connector=Gateway(answers),
        attr_id=path,
        db=database,
        _type=kind,
        bus_type=CAN,
        current_date=now,
    )
    await made.update()
    return made


def heating(program):
    path = "/heatingCircuits/hc2"
    return {
        f"{path}/activeSwitchProgram": program,
        f"{path}/temperatureLevels/normal": number(
            f"{path}/temperatureLevels/normal", 21.5, 10.0, 30.0
        ),
        f"{path}/temperatureLevels/exception": number(
            f"{path}/temperatureLevels/exception", 17.0, 10.0, 30.0
        ),
        f"{path}/status": value(f"{path}/status", "ACTIVE"),
    }


@pytest.mark.asyncio
async def test_a_mode_never_read_is_none_not_off():
    hc2 = await circuit(HC, "/heatingCircuits/hc2", heating(UNDECODABLE))
    assert hc2.ha_mode is None


@pytest.mark.asyncio
async def test_a_mode_read_is_kept_when_a_later_read_fails():
    answers = heating(
        value("/heatingCircuits/hc2/activeSwitchProgram", "HP_OPTIMIZED", PROGRAMS)
    )
    hc2 = await circuit(HC, "/heatingCircuits/hc2", answers)
    assert hc2.ha_mode == "auto"
    answers["/heatingCircuits/hc2/activeSwitchProgram"] = UNDECODABLE
    await hc2.update()
    assert hc2.ha_mode == "auto"


@pytest.mark.asyncio
async def test_hot_water_on_automatic_has_no_target():
    path = "/dhwCircuits/dhwA"
    answers = {
        f"{path}/operationMode": value(
            f"{path}/operationMode",
            "Automatic",
            ["Automatic", "Always_On", "Always_Off"],
        ),
        f"{path}/activeDhwTimeProgram": value(
            f"{path}/activeDhwTimeProgram",
            "AlwaysHotWater",
            ["AlwaysHotWater", "Program1", "Program2"],
        ),
        f"{path}/setTemperature": number(f"{path}/setTemperature", -5.0, 45.0, 59.0),
        f"{path}/actualTemp": number(f"{path}/actualTemp", 50.0),
        f"{path}/extraDhw/status": value(f"{path}/extraDhw/status", "OFF"),
    }
    dhw = await circuit(DHW, path, answers)
    assert dhw.ha_mode == "performance"
    assert dhw.target_temperature is None
