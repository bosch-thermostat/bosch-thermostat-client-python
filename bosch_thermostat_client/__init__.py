"""Python library to control Bosch driven thermostats."""
from .exceptions import (
    BoschException,
    DeviceConnectionError,
    DeviceException,
    FailedAuthException,
    FirmwareException,
    ResponseException,
    EncryptionException,
    MsgConnectionError,
    MsgException,
    UnknownDevice,
)
from .connectors.easycontrol import easycontrol_ssl_context
from .gateway import gateway_chooser

from .version import __version__ as version

name = "bosch_thermostat_client"


__all__ = [
    "gateway_chooser",
    "easycontrol_ssl_context",
    "version",
    "BoschException",
    "DeviceConnectionError",
    "DeviceException",
    "FailedAuthException",
    "ResponseException",
    "EncryptionException",
    "FirmwareException",
    "MsgConnectionError",
    "MsgException",
    "UnknownDevice",
]
