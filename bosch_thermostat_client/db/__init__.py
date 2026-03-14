"""Retrieve standard data."""

import asyncio
import logging
import json
import os

from bosch_thermostat_client.const import DEFAULT, FIRMWARE_VERSION
from bosch_thermostat_client.const.nefit import NEFIT
from bosch_thermostat_client.const.ivt import (
    CAN,
    IVT,
    NSC_ICOM_GATEWAY,
    RC300_RC200,
    MBLAN,
    IVTAIR,
    BRUDERUS
)
from bosch_thermostat_client.const.easycontrol import EASYCONTROL

_LOGGER = logging.getLogger(__name__)

MAINPATH = os.path.join(os.path.dirname(__file__))

DEVICE_TYPES = {
    RC300_RC200: "rc300_rc200/{}.json",
    DEFAULT: "default/{}.json",
    CAN: "can/{}.json",
    MBLAN: "mblan/{}.json",
    NEFIT: "nefit/{}.json",
    NSC_ICOM_GATEWAY: "nsc_icom_gateway/{}.json",
    EASYCONTROL: "easycontrol/{}.json",
    IVTAIR: "ivtair/{}.json",
    BRUDERUS: "bruderus/{}.json",
}


async def async_open_json(file):
    return await asyncio.to_thread(open_json, file)


def open_json(file):
    """Open json file."""
    try:
        with open(file, "r") as db_file:
            datastore = json.load(db_file)
            return datastore
    except FileNotFoundError:
        pass
    return {}


async def get_initial_db(device_type):
    filename = os.path.join(MAINPATH, f"db_{device_type}.json")
    """Get initial db. Same for all devices."""
    return await async_open_json(filename)


async def get_db_of_firmware(device_type, firmware_version):
    """Get db of specific device."""
    if not firmware_version:
        _LOGGER.error("Can't find your fw version.")
        return None
    filename = DEVICE_TYPES[device_type].format(firmware_version.replace(".", ""))
    filepath = os.path.join(MAINPATH, filename)
    _LOGGER.debug("Attempt to load database from file %s", filepath)
    _db = await async_open_json(filepath)
    return _db if _db.get(FIRMWARE_VERSION) == firmware_version else None


def get_custom_db(firmware_version, _db):
    """Get db of device if yours doesn't exists."""
    if _db:
        if firmware_version in _db:
            return _db[firmware_version]
    return None


def get_ivt_errors() -> dict:
    """Get error codes of IVT devices."""
    return open_json(os.path.join(MAINPATH, "errorcodes_ivt.json"))


def get_nefit_errors() -> dict:
    """Get error codes of NEFIT devices."""
    return open_json(os.path.join(MAINPATH, "errorcodes_nefit.json"))


def get_easycontrol_errors() -> dict:
    """Get error codes of EASYCONTROL devices."""
    return open_json(os.path.join(MAINPATH, "errorcodes_easycontrol.json"))


async def async_get_errors(device_type) -> dict:
    """Get error codes of all devices."""
    if device_type == EASYCONTROL:
        return await asyncio.to_thread(get_easycontrol_errors)
    elif device_type == NEFIT:
        return await asyncio.to_thread(get_nefit_errors)
    elif device_type == IVT:
        return (await asyncio.to_thread(get_nefit_errors)) | (
            await asyncio.to_thread(get_ivt_errors)
        )
    return {}
