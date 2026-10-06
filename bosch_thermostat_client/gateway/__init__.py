from .ivt import IVTGateway, IVTMBLanGateway
from .pointtapi import PoinTTAPIGateway
from .nefit import NefitGateway
from .easycontrol import EasycontrolGateway
from bosch_thermostat_client.const.ivt import IVT, IVT_MBLAN
from bosch_thermostat_client.const import POINTTAPI
from bosch_thermostat_client.const.nefit import NEFIT
from bosch_thermostat_client.const.easycontrol import EASYCONTROL


def gateway_chooser(device_type=IVT):
    return {
        IVT: IVTGateway,
        NEFIT: NefitGateway,
        EASYCONTROL: EasycontrolGateway,
        IVT_MBLAN: IVTMBLanGateway,
        POINTTAPI: PoinTTAPIGateway,
    }[device_type]
