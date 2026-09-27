"""Gateway module connecting to Bosch thermostat."""

import logging
from .base import BaseGateway

from bosch_thermostat_client.connectors import NefitConnector, HttpConnector
from bosch_thermostat_client.encryption import NefitEncryption as Encryption
from bosch_thermostat_client.const import (
    HTTP,
    XMPP,
    GATEWAY,
    MODELS,
    EMS,
    SYSTEM_BUS,
    VALUE,
    REFERENCES,
    ID,
    HC,
    DHW,
    SENSORS,
)
from bosch_thermostat_client.const.nefit import NEFIT, PRODUCT_ID, CIRCUIT_TYPES
from bosch_thermostat_client.exceptions import DeviceException


_LOGGER = logging.getLogger(__name__)


class NefitGateway(BaseGateway):
    """Gateway to Bosch thermostat."""

    device_type = NEFIT
    circuit_types = CIRCUIT_TYPES

    def __init__(
        self,
        host,
        access_token,
        session_type=XMPP,
        access_key=None,
        password=None,
        session=None,
        ssl_context=None,
    ):
        """
        Initialize gateway.

        :param access_token:
        :param password:
        :param host:
        :param device_type -> NEFIT
        """
        self._access_token = access_token.replace("-", "")

        if password:
            access_key = self._access_token
        if session_type == HTTP:
            _LOGGER.warn("I'm using HTTP connector. It's probably debug session!")
            nefit_connector = HttpConnector
        else:
            nefit_connector = NefitConnector
        self._connector = nefit_connector(
            host=host,
            loop=session,
            access_key=self._access_token,
            encryption=Encryption(access_key, password),
            device_type=NEFIT,
            ssl_context=ssl_context,
        )
        self._session_type = session_type
        self._data = {GATEWAY: {}, HC: None, DHW: None, SENSORS: None}
        super().__init__(host)

    async def _update_info(self, initial_db):
        """Update gateway info from Bosch device."""
        for name, uri in initial_db.items():
            try:
                response = await self._connector.get(uri)
                if VALUE in response:
                    self._data[GATEWAY][name] = response[VALUE]
                elif name == SYSTEM_BUS:
                    self._data[GATEWAY][SYSTEM_BUS] = response.get(REFERENCES, [])
            except DeviceException as err:
                _LOGGER.debug("Can't fetch data for update_info %s", err)
                pass

    def get_device_model(self, _db):
        """Find device model."""
        product_id = self._data[GATEWAY].get(PRODUCT_ID)
        model_scheme = _db[MODELS]
        for bus in self._data[GATEWAY].get(SYSTEM_BUS, []):
            if EMS in bus.get(ID, "").upper():
                self._bus_type = EMS
                break
        if not self._bus_type:
            _LOGGER.error(
                "Couldn't fetch bus connection. Something wrong. Got product ID: %s. %s",
                product_id,
                "I will guess bus type.",
            )
            self._bus_type = EMS

        if self._bus_type == EMS and product_id in model_scheme:
            return model_scheme.get(product_id)
        _LOGGER.error(f"Couldn't find device model. Got product ID: {product_id}")
