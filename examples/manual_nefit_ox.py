"""Manual test script of bosch_thermostat_client Nefit connection with HTTP endpoint. """
import asyncio
import logging
import aiohttp
import bosch_thermostat_client as bosch
from bosch_thermostat_client.const.nefit import NEFIT
from bosch_thermostat_client.const import HC, HTTP, DHW

logging.basicConfig()
logging.getLogger().setLevel(logging.WARN)


async def circuits_init(gateway, circ_type=HC):
    await gateway.initialize_circuits(circ_type)


async def get_circuit(gateway, c_index, circ_type=HC):
    circs = gateway.get_circuits(circ_type)
    circ = circs[c_index]
    await circ.update()
    return circ


async def circuits_read_temp(gateway, c_index, circ_type=HC):
    circ = await get_circuit(gateway, c_index, circ_type)
    print(f"{circ_type} Current temp: ", circ.current_temp)
    print(f"{circ_type} Traget temp: ", circ.target_temperature)


async def get_operation_mode(gateway, c_index, circ_type=HC):
    circ = await get_circuit(gateway, c_index, circ_type)
    print(f"{circ_type} Operation mode: ", circ.ha_mode)


async def set_operation_mode(gateway, c_index, circ_type=HC):
    circ = await get_circuit(gateway, c_index, circ_type)
    mode = "auto" if circ.ha_mode == "heat" else "heat"
    await circ.set_ha_mode(mode)


async def test_circ(gateway, circ_type=HC):
    print(f"=================={circ_type}==================")
    await circuits_init(gateway, circ_type)
    await circuits_read_temp(gateway, 0, circ_type)
    await get_operation_mode(gateway, 0, circ_type)
    await set_operation_mode(gateway, 0, circ_type)
    print("=======================================")


async def main():
    """"""
    BoschGateway = bosch.gateway_chooser(device_type=NEFIT)
    async with aiohttp.ClientSession() as session:
        gateway = BoschGateway(
            session=session,
            session_type=HTTP,
            host="127.0.0.1:8080",
            access_token="ABCdEFGHIJHKL2MN",
            password="abcdef12",
        )
        # 1. Check if auto mode.
        # 2. Adjust temperature by half 0.5 C
        # 3. Wait 60s.
        # 4. Switch to manual mode
        # 5. Wait 60s
        # 6. Switch to auto mode
        # 7. Check fetched temp.
        await gateway.initialize()
        await test_circ(gateway, HC)
        await test_circ(gateway, DHW)

        # await set_operation_mode(gateway, 0, DHW)
        return


asyncio.run(main())

# asyncio.get_event_loop().run_until_complete(main())
