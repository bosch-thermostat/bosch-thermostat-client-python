from .http import HttpConnector
from .ivt import IVTXMPPConnector
from .nefit import NefitConnector
from .easycontrol import EasycontrolConnector
from .oauth2 import Oauth2Connector

from bosch_thermostat_client.const import HTTP, OAUTH2


def connector_ivt_chooser(session_type):
    if session_type.upper() == OAUTH2:
        return Oauth2Connector
    elif session_type.upper() == HTTP:
        return HttpConnector
    else:
        return IVTXMPPConnector


__all__ = [
    "NefitConnector",
    "IVTXMPPConnector",
    "HttpConnector",
    "EasycontrolConnector",
    "Oauth2Connector",
]
