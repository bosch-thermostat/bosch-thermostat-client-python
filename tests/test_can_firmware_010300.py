import pytest

from bosch_thermostat_client.const.ivt import CAN
from bosch_thermostat_client.db import get_db_of_firmware


@pytest.mark.asyncio
async def test_firmware_010300_has_a_database():
    database = await get_db_of_firmware(CAN, "01.03.00")
    assert database is not None
    assert database["versionFirmware"] == "01.03.00"


@pytest.mark.asyncio
async def test_firmware_010300_reads_no_path_it_does_not_answer():
    database = await get_db_of_firmware(CAN, "01.03.00")
    heating = {ref["id"] for ref in database["heatingCircuits"]["refs"].values()}
    hot_water = {ref["id"] for ref in database["dhwCircuits"]["refs"].values()}
    assert "operationMode" not in heating
    assert "currentSetpoint" not in hot_water
    assert "activatedTemperatureLevel" not in hot_water
