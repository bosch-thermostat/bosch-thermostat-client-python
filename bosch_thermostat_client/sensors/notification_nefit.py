from bosch_thermostat_client.db import get_nefit_errors
from .sensor import Sensor
from bosch_thermostat_client.const import (
    MIN_VALUE,
    RESULT,
    TYPE,
    URI,
    VALUE,
)


class NotificationSensor(Sensor):
    errorcodes: dict
    _allowed_types = "notification"

    def __init__(
        self,
        attr_id,
        path,
        device_class=None,
        state_class=None,
        kind="notification",
        **kwargs
    ):
        """
        Single sensor init.

        :param dics requests: { GET: get function, SUBMIT: submit function}
        :param str path: path to retrieve data from sensor.
        """
        cause_uri = kwargs.get("cause")
        super().__init__(
            path=path,
            attr_id=attr_id,
            device_class=device_class,
            state_class=state_class,
            kind=kind,
            **kwargs,
        )
        self._data = {
            attr_id: {RESULT: {}, URI: path, TYPE: kind},
            "cause": {RESULT: {}, URI: cause_uri, TYPE: kind},
        }
        self.errorcodes = kwargs.get("errorcodes", {})

    @property
    def state(self):
        """Retrieve state of the circuit."""
        result = self._data[self.attr_id].get(RESULT)
        if VALUE in result:
            val = result.get(VALUE, "")
            if not val:
                return "No notifications"
            if val in self.errorcodes:
                row = self.errorcodes[val]
                cause = self._data["cause"].get(RESULT)
                if (
                    cause.get(VALUE, 0) > cause.get(MIN_VALUE, 200)
                    and str(cause.get(VALUE, 0)) in row
                ):
                    return row[str(cause.get(VALUE, 0))].get("description", "")
            return val
        return "No notifications"
