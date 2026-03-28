"""Gateway module connecting to Bosch thermostat."""

import json
import logging

from bosch_thermostat_client.connectors import connector_ivt_chooser
from bosch_thermostat_client.const import (
    DHW,
    EMS,
    GATEWAY,
    HC,
    MODELS,
    SENSORS,
    SYSTEM_BUS,
    VALUE,
    VALUES,
)
from bosch_thermostat_client.const.ivt import (
    CAN,
    CIRCUIT_TYPES,
    IVT,
    IVT_MBLAN,
    SYSTEM_INFO,
)
from bosch_thermostat_client.encryption import IVTEncryption as Encryption
from bosch_thermostat_client.exceptions import DeviceException

from .base import BaseGateway

_LOGGER = logging.getLogger(__name__)


class IVTGateway(BaseGateway):
    """IVT Gateway"""

    device_type = IVT
    circuit_types = CIRCUIT_TYPES

    def __init__(
        self,
        session_type,
        host,
        access_token,
        access_key=None,
        password=None,
        session=None,
        ssl_context=None,
    ):
        """IVT Gateway constructor

        Args:
            session (loop): loop or websession
            session_type (str): either HTTP or XMPP
            host (str): host IP or hostname for HTTP or serial number for XMPP
            access_key (str): access key to Bosch Gateway
            password (str, optional): Password to Bosch Gateway. Defaults to None.
        """
        self._access_token = access_token.replace("-", "")
        if password:
            access_key = self._access_token
        Connector = connector_ivt_chooser(session_type)
        self._session_type = session_type
        self._connector = Connector(
            host=host,
            loop=session,
            access_key=self._access_token,
            encryption=Encryption(access_key, password),
            ssl_context=ssl_context,
        )
        self._data = {GATEWAY: {}, HC: None, DHW: None, SENSORS: None}
        super().__init__(host)

    async def _update_info(self, initial_db):
        """Update gateway info from Bosch device."""
        for name, uri in initial_db.items():
            try:
                response = await self._connector.get(uri)
                if VALUE in response:
                    self._data[GATEWAY][name] = response[VALUE]
                elif name == SYSTEM_INFO:
                    self._data[GATEWAY][SYSTEM_INFO] = response.get(VALUES, [])
            except DeviceException as err:
                _LOGGER.debug("Can't fetch data for update_info %s", err)
                pass

    def get_device_model(self, _db):
        """Find device model."""
        system_bus = self._data[GATEWAY].get(SYSTEM_BUS)
        model_scheme = _db[MODELS]
        if system_bus == CAN:
            self._bus_type = CAN
            return model_scheme.get(CAN)
        self._bus_type = EMS
        system_info = self._data[GATEWAY].get(SYSTEM_INFO)
        attached_devices = {}
        if system_info:
            for info in system_info:
                _id = info.get("Id", -1)
                model = model_scheme.get(_id)
                if model is not None:
                    _LOGGER.debug("Found supported device %s with id %s", model, _id)
                    attached_devices[_id] = model
            if attached_devices:
                if "158" in attached_devices:
                    found_model = attached_devices["158"]
                else:
                    found_model = attached_devices[sorted(attached_devices.keys())[-1]]
                _LOGGER.debug("Using model %s as database schema", found_model[VALUE])
                return found_model
        _LOGGER.error(
            "I cannot find supported device. Your devices: %s", json.dumps(system_info)
        )


class IVTMBLanGateway(IVTGateway):
    device_type = IVT_MBLAN

    def get_device_model(self, _db):
        """Find device model."""
        model_scheme = _db[MODELS]
        self._bus_type = EMS
        system_info = self._data[GATEWAY].get(SYSTEM_INFO)
        if system_info and system_info == "iCom_Low_v1":
            return model_scheme.get("iCom_Low_v1")
        _LOGGER.error(
            "I cannot find supported device. Your devices: %s", json.dumps(system_info)
        )
