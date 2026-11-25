import pytest
from aiohttp import ClientSession

from bosch_thermostat_client.const import GATEWAY, HTTP
from bosch_thermostat_client.const.ivt import CAN
from bosch_thermostat_client.db import get_initial_db
from bosch_thermostat_client.gateway.ivt import IVTGateway


async def model_for(gateway_data):
    async with ClientSession() as session:
        gateway = IVTGateway(
            session=session,
            session_type=HTTP,
            host="gateway.invalid",
            access_token="token",
        )
        gateway._data[GATEWAY].update(gateway_data)
        model = gateway.get_device_model(await get_initial_db("IVT"))
        return model, gateway._bus_type


@pytest.mark.asyncio
async def test_the_system_bus_says_can():
    model, bus = await model_for({"systemBus": "CAN"})
    assert model["type"] == CAN
    assert bus == CAN


@pytest.mark.asyncio
async def test_a_can_gateway_without_a_system_bus_is_told_by_its_hardware():
    model, bus = await model_for({"versionHardware": "iCom_low_CAN_v1"})
    assert model["type"] == CAN
    assert bus == CAN


@pytest.mark.asyncio
async def test_a_system_bus_said_otherwise_is_not_overridden_by_the_hardware():
    model, bus = await model_for(
        {"systemBus": "EMS", "versionHardware": "iCom_low_CAN_v1"}
    )
    assert model is None
    assert bus != CAN


@pytest.mark.asyncio
async def test_neither_bus_nor_hardware_finds_no_model():
    model, _ = await model_for({})
    assert model is None
