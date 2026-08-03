from .http import HttpConnector
from .ivt import IVTXMPPConnector
from .nefit import NefitConnector
from .easycontrol import EasycontrolConnector
from .pointtapi import PoinTTAPIConnector

from bosch_thermostat_client.const import HTTP, POINTTAPI


def connector_ivt_chooser(session_type):
    if session_type.upper() == POINTTAPI:
        return PoinTTAPIConnector
    elif session_type.upper() == HTTP:
        return HttpConnector
    else:
        return IVTXMPPConnector


__all__ = [
    "NefitConnector",
    "IVTXMPPConnector",
    "HttpConnector",
    "EasycontrolConnector",
    "PoinTTAPIConnector",
]
