"""Manual test script of bosch_thermostat_client Nefit connection with HTTP endpoint. """

import asyncio
import logging
from datetime import datetime, timedelta
import time
import bosch_thermostat_client as bosch
from bosch_thermostat_client.const.ivt import IVT
from bosch_thermostat_client.const import HC, XMPP, DHW

logging.basicConfig()
logging.getLogger().setLevel(logging.WARN)


async def hc_circuits_init(gateway):
    await gateway.initialize_circuits(HC)


async def dhw_circuits_init(gateway):
    await gateway.initialize_circuits(DHW)


async def get_circuit(gateway, c_index, circ_type=HC):
    circs = gateway.get_circuits(circ_type)
    circ = circs[c_index]
    await circ.update()
    return circ


async def dhw_circuit_test(gateway):
    dhw = await get_circuit(gateway, 0, DHW)
    sws = dhw.switches


async def hc_circuits_read_temp(gateway, c_index, circ_type=HC):
    hc = await get_circuit(gateway, c_index, circ_type)
    print("hvac mode", hc.current_temp)
    print("target temp ->", hc.target_temperature)


async def get_operation_mode(gateway, c_index, circ_type=HC):
    hc = await get_circuit(gateway, c_index, circ_type)
    print("OPERATION MODE", hc.ha_mode)


async def set_operation_mode(gateway, c_index, circ_type=HC):
    hc = await get_circuit(gateway, c_index, circ_type)
    print("OPERATION MODE", hc.ha_mode)
    mode = "auto" if hc.ha_mode == "heat" else "heat"
    await hc.set_ha_mode(mode)


async def main():
    """"""
    BoschGateway = bosch.gateway_chooser(device_type=IVT)
    gateway = BoschGateway(
        session=None,
        session_type=XMPP,
        host="aaa",
        access_token="a",
        password="a",
    )
    await gateway.initialize()
    await gateway.get_capabilities()
    sensors = gateway.sensors

    def find_ch_rec():
        for sensor in sensors:
            if sensor.name == "ractualCHPower":
                return sensor

    recording_sensor = find_ch_rec()
    start = datetime.fromisoformat("2024-03-27T00:00:00+01:00")
    stop = datetime.fromisoformat("2024-03-29T22:06:24+01:00")
    range = await recording_sensor.fetch_range(start, stop)
    print(range)

    #        await hc.set_ha_mode("auto") #MEANS AUTO
    #       await hc.update()
    # time.sleep(4)
    # return
    # return
    # await dhw.set_ha_mode("performance") #MEANS MANUAL
    return
    # print("target in manual", hc.target_temperature)
    # print("ha mode in manual", hc.ha_mode)
    # await hc.update()
    # print("target after update", hc.target_temperature)
    # print("ha mode", hc.ha_mode)

    # await hc.set_ha_mode("auto") #MEANS AUTO
    # print("target after auto without update", hc.target_temperature)
    # print("ha mode", hc.ha_mode)

    # return
    # print(await hc.set_temperature(10.0))
    # print("ustawiona!")
    dhws = gateway.dhw_circuits
    dhw = dhws[0]
    await dhw.update()
    print("START1")
    print(dhw.target_temperature)
    print("START2")
    print(dhw.current_mode)
    print(dhw.target_temperature)

    return
    print("START3")
    print(dhw.target_temperature)
    return
    # print(hc.schedule)
    print(gateway.get_info(DATE))
    # print(await gateway.rawscan())
    # print(hc.schedule.get_temp_for_date(gateway.get_info(DATE)))
    return
    aa = 0
    while aa < 10:
        time.sleep(1)
        await hc.update()
        print(hc.target_temperature)
        aa = aa + 1

    await hc.set_operation_mode("auto")

    aa = 0
    while aa < 10:
        time.sleep(1)
        await hc.update()
        print(hc.target_temperature)
        aa = aa + 1

    # print(gateway.get_property(TYPE_INFO, UUID))
    await loop.close()


asyncio.run(main())

# asyncio.get_event_loop().run_until_complete(main())
