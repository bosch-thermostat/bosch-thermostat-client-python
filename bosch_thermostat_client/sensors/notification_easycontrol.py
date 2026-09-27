from bosch_thermostat_client.db import (
    get_easycontrol_errors,
)
from bosch_thermostat_client.const.ivt import INVALID
from .sensor import Sensor
from bosch_thermostat_client.const import (
    RESULT,
    VALUE,
)


class NotificationSensor(Sensor):
    errorcodes: dict

    def __init__(
        self,
        **kwargs,
    ) -> None:
        """Notification sensor init."""
        super().__init__(**kwargs)
        self.errorcodes = kwargs.get("errorcodes", {})

    def get_error_message(self, dcd: str, ccd: str, act: str, fc: str) -> str:
        msg = "Unknown error"
        _dcd_lvl = self.errorcodes.get(dcd)
        if not _dcd_lvl:
            return msg
        _ccd_lvl = _dcd_lvl.get(ccd)
        if not _ccd_lvl:
            return msg
        if len(_ccd_lvl) == 1:
            return _ccd_lvl[0]["message"]
        for row in _ccd_lvl:
            _failure_type = row["failure-type"]
            _error_class = row["error-class"]
            if act == _failure_type and fc == _error_class:
                return row["message"]
            if act == _failure_type or fc == _error_class:
                # if not both, save as message
                msg = row["message"]
        return msg

    def process_results(self, result, key=None, return_data=False):
        """Convert multi-level json object to one level object."""
        data = {RESULT: {}} if return_data else self._data[key]
        updated = False
        if result:
            vals = result.get(VALUE, [])
            if vals:
                data[RESULT] = {}
                for idx, val in enumerate(vals):
                    if "ccd" in val:
                        key_suffix = "" if idx == 0 else f"_{idx}"
                        data[RESULT][f"{VALUE}{key_suffix}"] = (
                            self.get_error_message(
                                dcd=str(val.get("dcd", "")),
                                ccd=str(val.get("ccd", "")),
                                act=str(val.get("act", "")),
                                fc=str(val.get("fc", "")),
                            )
                        )
                        data[RESULT]["fullError"] = val
                    else:
                        data[RESULT] = {VALUE: val}
            else:
                data[RESULT] = {VALUE: "No notifications"}
            self._update_initialized = True
            updated = True
        else:
            data[RESULT] = {VALUE: "Unknown"}
        return data[RESULT] if return_data else updated

    @property
    def state(self):
        """Retrieve state of the circuit."""
        result = self._data[self.attr_id].get(RESULT)
        if VALUE in result:
            return result.get(VALUE, INVALID)
        return result
