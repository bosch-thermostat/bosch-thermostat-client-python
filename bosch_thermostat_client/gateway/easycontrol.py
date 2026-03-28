"""Gateway module connecting to Bosch thermostat."""

import logging

from bosch_thermostat_client.connectors import EasycontrolConnector, HttpConnector
from bosch_thermostat_client.const import (
    DHW,
    EMS,
    GATEWAY,
    HTTP,
    ID,
    MODELS,
    REFERENCES,
    SENSORS,
    SYSTEM_BUS,
    VALUE,
    XMPP,
    ZN,
)
from bosch_thermostat_client.const.easycontrol import (
    CIRCUIT_TYPES,
    EASYCONTROL,
    PRODUCT_ID,
    DV
)
from bosch_thermostat_client.encryption import EasycontrolEncryption as Encryption
from bosch_thermostat_client.exceptions import DeviceException

from .base import BaseGateway

_LOGGER = logging.getLogger(__name__)


class EasycontrolGateway(BaseGateway):
    """Gateway to Bosch thermostat."""

    device_type = EASYCONTROL
    circuit_types = CIRCUIT_TYPES

    def __init__(
        self,
        host,
        access_token,
        session_type=XMPP,
        access_key=None,
        password=None,
        session=None,
        easycontrol_connector=None,
        ssl_context=None,
    ):
        """
        Initialize gateway.

        :param access_token:
        :param password:
        :param host:
        :param device_type -> IVT or NEFIT or EASYCONTROL
        """
        self._access_token = access_token.replace("-", "")
        if password:
            access_key = self._access_token
        if session_type == HTTP:
            _LOGGER.warn("I'm using HTTP connector. It's probably debug session!")
            easycontrol_connector = HttpConnector
        else:
            easycontrol_connector = EasycontrolConnector
        self._connector = easycontrol_connector(
            host=host,
            loop=session,
            access_key=self._access_token,
            encryption=Encryption(access_key, password),
            device_type=EASYCONTROL,
            ssl_context=ssl_context,
        )
        self._session_type = session_type
        self._data = {GATEWAY: {}, ZN: None, DHW: None, DV: None, SENSORS: None}
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
        model = None
        for bus in self._data[GATEWAY].get(SYSTEM_BUS, []):
            if EMS in bus.get(ID, "").upper():
                self._bus_type = EMS
                break
        if self._bus_type == EMS:
            model = model_scheme.get(product_id)
        if not model:
            _LOGGER.error(f"Couldn't find device model. Got product ID: {product_id}")
        return model

    @property
    def heating_circuits(self):
        """Get circuit list."""
        return self._data[ZN].circuits
