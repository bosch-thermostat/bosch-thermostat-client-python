import click
import logging
import aiohttp
import bosch_thermostat_client as bosch
from bosch_thermostat_client.db import open_json, MAINPATH
from bosch_thermostat_client.const import HC, HTTP, SENSORS, DHW
from bosch_thermostat_client.const.nefit import NEFIT
from bosch_thermostat_client.const.ivt import IVT
import os
import asyncio

from functools import wraps

_LOGGER = logging.getLogger(__name__)

pass_bosch = click.make_pass_decorator(dict, ensure=True)


def coro(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        return asyncio.run(f(*args, **kwargs))

    return wrapper


@click.group(invoke_without_command=True)
@click.pass_context
@coro
async def cli(ctx):
    """A tool to create rawscan of Bosch thermostat."""
    pass


@cli.command()
@click.option(
    "--host", envvar="BOSCH_HOST", type=str, required=True, help="IP address of gateway"
)
@click.option(
    "--token",
    envvar="BOSCH_ACCESS_TOKEN",
    type=str,
    required=True,
    help="Token from sticker without dashes.",
)
@click.option(
    "--password",
    envvar="BOSCH_PASSWORD",
    type=str,
    required=False,
    help="Password you set in mobile app.",
)
@click.option(
    "--device",
    envvar="BOSCH_DEVICE",
    type=click.Choice([NEFIT, IVT], case_sensitive=False),
    required=True,
    help="Bosch device type. NEFIT or IVT.",
)
@click.option("-d", "--debug", default=False, count=True)
@click.pass_context
@coro
async def sensors(ctx, host: str, token: str, password: str, debug: int, sensor):
    if debug:
        logging.basicConfig(level=logging.DEBUG)
        _LOGGER.info("Debug mode active")
        _LOGGER.debug(f"Lib version is {bosch.version}")
    else:
        logging.basicConfig(level=logging.INFO)
    async with aiohttp.ClientSession() as session:
        if device.upper() == NEFIT or device.upper() == IVT:
            BoschGateway = bosch.gateway_chooser(device_type=device)
        gateway = bosch.Gateway(
            session=session, host=host, access_key=token, password=password
        )
        _LOGGER.debug("Trying to connect to gateway.")
        if await gateway.check_connection():
            _LOGGER.info(
                "Successfully connected to gateway. Found UUID: %s", gateway.uuid
            )
            sensors = gateway.initialize_sensors(list(sensor))
            for sensor_obj in sensors:
                await sensor_obj.update()
                print(sensor_obj.name, ":", sensor_obj.get_property(sensor_obj.attr_id))
        else:
            _LOGGER.error("Couldn't connect to gateway!")
        await session.close()


@cli.command()
@click.option(
    "--host", envvar="BOSCH_HOST", type=str, required=True, help="IP address of gateway"
)
@click.option(
    "--token",
    envvar="BOSCH_ACCESS_TOKEN",
    type=str,
    required=True,
    help="Token from sticker without dashes.",
)
@click.option(
    "--password",
    envvar="BOSCH_PASSWORD",
    type=str,
    required=False,
    help="Password you set in mobile app.",
)
@click.option(
    "--device",
    envvar="BOSCH_DEVICE",
    type=click.Choice([NEFIT, IVT], case_sensitive=False),
    required=True,
    help="Bosch device type. NEFIT or IVT.",
)
@click.option("-d", "--debug", default=False, count=True)
@click.pass_context
@coro
async def switches(ctx, host: str, token: str, password: str, debug: int, device: str):
    if debug:
        logging.basicConfig(level=logging.DEBUG)
        _LOGGER.info("Debug mode active")
        _LOGGER.debug(f"Lib version is {bosch.version}")
    else:
        logging.basicConfig(level=logging.INFO)
    async with aiohttp.ClientSession() as session:
        if device.upper() == NEFIT or device.upper() == IVT:
            BoschGateway = bosch.gateway_chooser(device_type=device)
        gateway = BoschGateway(
            session=session,
            session_type=HTTP,
            host=host,
            access_token=token,
            password=password,
        )
        _LOGGER.debug("Trying to connect to gateway.")
        if await gateway.check_connection():
            _LOGGER.info(
                "Successfully connected to gateway. Found UUID: %s", gateway.uuid
            )
            await gateway.initialize_switches()
            switches = gateway.switches
            print(switches.selects)
        else:
            _LOGGER.error("Couldn't connect to gateway!")
        await session.close()


@cli.command()
@click.option(
    "--ip", envvar="BOSCH_IP", type=str, required=True, help="IP address of gateway"
)
@click.option(
    "--token",
    envvar="BOSCH_ACCESS_TOKEN",
    type=str,
    required=True,
    help="Token from sticker without dashes.",
)
@click.option(
    "--password",
    envvar="BOSCH_PASSWORD",
    type=str,
    required=False,
    help="Password you set in mobile app.",
)
@click.option("-d", "--debug", default=False, count=True)
@click.option(
    "-t", "--target_temp", default=False, count=True, help="Get target temperature"
)
@click.option("-m", "--op_mode", default=False, count=True, help="Print current mode")
@click.option(
    "--op_modes", default=False, count=True, help="Print available operation modes"
)
@click.option(
    "--setpoints", default=False, count=True, help="Print setpoints from schedule"
)
@click.pass_context
@coro
async def hc(
    ctx,
    ip: str,
    token: str,
    password: str,
    debug: int,
    target_temp: int,
    op_mode: int,
    op_modes: int,
    setpoints: int,
):
    if debug:
        logging.basicConfig(level=logging.DEBUG)
        _LOGGER.info("Debug mode active")
        _LOGGER.debug(f"Lib version is {bosch.version.__version__}")
    else:
        logging.basicConfig(level=logging.INFO)
    async with aiohttp.ClientSession() as session:
        gateway = bosch.Gateway(
            session=session, host=ip, access_key=token, password=password
        )
        _LOGGER.debug("Trying to connect to gateway.")
        if await gateway.check_connection():
            _LOGGER.info(
                "Successfully connected to gateway. Found UUID: %s", gateway.uuid
            )
            await circuit_fetch(gateway, HC, target_temp, op_mode, op_modes, setpoints)
        else:
            _LOGGER.error("Couldn't connect to gateway!")
        await session.close()


@cli.command()
@click.option(
    "--ip", envvar="BOSCH_IP", type=str, required=True, help="IP address of gateway"
)
@click.option(
    "--token",
    envvar="BOSCH_ACCESS_TOKEN",
    type=str,
    required=True,
    help="Token from sticker without dashes.",
)
@click.option(
    "--password",
    envvar="BOSCH_PASSWORD",
    type=str,
    required=False,
    help="Password you set in mobile app.",
)
@click.option("-d", "--debug", default=False, count=True)
@click.option(
    "-t", "--target_temp", default=False, count=True, help="Get target temperature"
)
@click.option("-m", "--op_mode", default=False, count=True, help="Print current mode")
@click.option(
    "--op_modes", default=False, count=True, help="Print available operation modes"
)
@click.option(
    "--setpoints", default=False, count=True, help="Print setpoints from schedule"
)
@click.pass_context
@coro
async def dhw(
    ctx,
    ip: str,
    token: str,
    password: str,
    debug: int,
    target_temp: int,
    op_mode: int,
    op_modes: int,
    setpoints: int,
):
    if debug:
        logging.basicConfig(level=logging.DEBUG)
        _LOGGER.info("Debug mode active")
        _LOGGER.debug(f"Lib version is {bosch.version.__version__}")
    else:
        logging.basicConfig(level=logging.INFO)
    async with aiohttp.ClientSession() as session:
        gateway = bosch.Gateway(
            session=session, host=ip, access_key=token, password=password
        )
        _LOGGER.debug("Trying to connect to gateway.")
        if await gateway.check_connection():
            _LOGGER.info(
                "Successfully connected to gateway. Found UUID: %s", gateway.uuid
            )
            await circuit_fetch(gateway, DHW, target_temp, op_mode, op_modes, setpoints)
        else:
            _LOGGER.error("Couldn't connect to gateway!")
        await session.close()


async def circuit_fetch(
    gateway, circuit_type, target_temp, op_mode, op_modes, setpoints
):
    await gateway.initialize_circuits(circuit_type)
    circuits = gateway.get_circuits(circuit_type)
    for circuit in circuits:
        _LOGGER.debug("Fetching data from circuit.")
        await circuit.update()
        if target_temp:
            print(f"Target temp of {circuit.name} is: {circuit.target_temperature}")
        if op_mode:
            print(f"Operation mode of {circuit.name} is: {circuit.current_mode}")
        if op_modes:
            print(
                f"Available operation modes of {circuit.name} are: {circuit.available_operation_modes}"
            )
        if setpoints:
            print(
                f"Available setpoints of {circuit.name} are: {circuit.schedule.setpoints}"
            )


if __name__ == "__main__":
    asyncio.run(cli())
