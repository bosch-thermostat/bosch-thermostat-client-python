from __future__ import annotations
import logging
from bosch_thermostat_client.exceptions import DeviceException
from bosch_thermostat_client.helper import BoschSingleEntity, DeviceClassEntity
from bosch_thermostat_client.const import ID, RESULT, URI, TYPE, REGULAR, VALUE
from bosch_thermostat_client.const.ivt import INVALID

_LOGGER = logging.getLogger(__name__)

MISSING_ENDPOINT_ERROR_MARKERS = (
    "doesn not exist: 404",
    "does not exist: 404",
)
MISSING_ENDPOINT_WARNING_INTERVAL = 60


class Sensor(BoschSingleEntity, DeviceClassEntity):
    """Single sensor object."""

    def __init__(
        self,
        attr_id: str,
        path: str,
        device_class: str | None = None,
        state_class: str | None = None,
        entity_category: str | None = None,
        kind: str = REGULAR,
        data: dict | None = None,
        **kwargs,
    ) -> None:
        """
        Single sensor init.

        :param dics requests: { GET: get function, SUBMIT: submit function}
        :param str path: path to retrieve data from sensor.
        """
        BoschSingleEntity.__init__(self, path=path, attr_id=attr_id, **kwargs)
        DeviceClassEntity.__init__(
            self,
            device_class=device_class,
            state_class=state_class,
            entity_category=entity_category,
        )
        self._kind = kind
        self._device_class = device_class
        self._state_class = state_class
        if data:
            data[attr_id] = {RESULT: {}, URI: path, TYPE: kind}
            self._data = data
        else:
            self._data = {attr_id: {RESULT: {}, URI: path, TYPE: kind}}
        self._missing_endpoint_warning_counts: dict[str, int] = {}

    @staticmethod
    def _is_missing_endpoint_error(error: Exception) -> bool:
        error_text = str(error)
        return any(marker in error_text for marker in MISSING_ENDPOINT_ERROR_MARKERS)

    def _should_log_update_error(self, uri: str, error: Exception) -> bool:
        if not self._is_missing_endpoint_error(error):
            self._missing_endpoint_warning_counts.pop(uri, None)
            return True

        count = self._missing_endpoint_warning_counts.get(uri, 0) + 1
        self._missing_endpoint_warning_counts[uri] = count
        return count == 1 or count % MISSING_ENDPOINT_WARNING_INTERVAL == 0

    def _log_sensor_update_error(self, uri: str, error: Exception) -> None:
        log_level = (
            logging.WARNING
            if self._should_log_update_error(uri, error)
            else logging.DEBUG
        )
        _LOGGER.log(
            log_level,
            f"Can't update data for {self.name}. Trying uri: {uri}. Error message: {error}",
        )

    @property
    def kind(self) -> str:
        return self._kind

    @property
    def state(self) -> str:
        """Retrieve state of the circuit."""
        result = self._data[self.attr_id].get(RESULT)
        if result:
            return result.get(VALUE, INVALID)
        return "unavailable"

    async def update(self):
        """Update info about Sensor asynchronously."""
        item = self._data[self._main_data[ID]]
        if item[TYPE] in self._allowed_types:
            try:
                result = await self._connector.get(item[URI])
                self.process_results(result=result, key=self._main_data[ID])
                self._state = True
            except DeviceException as err:
                self._log_sensor_update_error(item[URI], err)
                self._extra_message = f"Can't update data. Error: {err}"
                self._state = False
