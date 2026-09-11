"""Logic to converse schedule."""
import logging
from datetime import datetime
from .easycontrol_programs import ZonePrograms

from bosch_thermostat_client.const import (
    MODE,
    SETPOINT,
    VALUE,
    DAYS_INT,
    ID,
    MAX,
    MIN,
    MAX_VALUE,
    MIN_VALUE,
    ON,
    URI,
    ACTIVE_PROGRAM,
    SWITCHPROGRAM_MODE,
    LEVELS,
    ABSOLUTE,
    REFS,
    DEFAULT_MAX_HC_TEMP,
    DEFAULT_MIN_HC_TEMP,
    SCHEDULE,
    PROGRAM,
    K_DAY,
    K_SETPOINT,
    K_TIME,
    OFF,
)

from bosch_thermostat_client.const.ivt import (
    DAYOFWEEK,
    TIME,
    TEMP,
    SETPOINT_PROP,
    SWITCH_POINTS,
    CAN,
)
from bosch_thermostat_client.exceptions import DeviceException

_LOGGER = logging.getLogger(__name__)

_CT200_DATE_FORMAT = "%Y-%m-%dT%H:%M:%S%z"
_CT200_NAIVE_DATE_FORMAT = "%Y-%m-%dT%H:%M:%S"


class Schedule:
    """Scheduler logic."""

    def __init__(
        self,
        connector,
        circuit_type,
        circuit_name,
        current_time,
        bus_type,
        db,
        op_mode,
        date_format: str = "%Y-%m-%dT%H:%M:%S",
    ):
        """Initialize schedule handling of Bosch gateway."""
        self._connector = connector
        self._active_program = None
        self._circuit_type = circuit_type
        self._circuit_name = circuit_name
        self._setpoints_temp = {}
        self._switch_points = None
        self._active_setpoint = None
        self._active_program_uri = None
        self._time = None
        self._time_retrieve = current_time
        self._bus_type = bus_type
        self._db = db
        self._schedule_def_db = self._db[SCHEDULE]
        self._op_mode = op_mode
        self._switchprogram_mode = self._schedule_def_db.get("default_mode", LEVELS)
        self._schedule_found = False
        self._program_uri = self._db[SCHEDULE][PROGRAM]
        self._day_key = self._schedule_def_db.get(K_DAY, DAYOFWEEK)
        self._setpoint_key = self._schedule_def_db.get(K_SETPOINT, SETPOINT)
        self._time_key = self._schedule_def_db.get(K_TIME, TIME)
        self._switchpoints_key = self._schedule_def_db.get(
            "switch_points", SWITCH_POINTS
        )
        self._date_format = date_format

    async def update_schedule(self, active_program):
        """Update schedule from Bosch gateway."""
        self._active_program = active_program
        self._active_program_uri = self._program_uri.format(
            self._circuit_name, active_program
        )
        if SWITCHPROGRAM_MODE in self._db[REFS]:
            try:
                switch_program_result = await self._connector.get(
                    f"/{self._circuit_type}/{self._circuit_name}/{SWITCHPROGRAM_MODE}"
                )
                self._switchprogram_mode = switch_program_result.get(VALUE, LEVELS)
            except DeviceException:
                pass
        try:
            self._time = await self._time_retrieve()
            result = await self._connector.get(self._active_program_uri)
            await self._parse_schedule(
                result.get(self._switchpoints_key, []), result.get(SETPOINT_PROP)
            )
            self._schedule_found = True
        except DeviceException:
            self._schedule_found = False
            _LOGGER.info(
                "URI for Active Program %s doesn't exists. Maybe we can figure it out how to work anyway",
                active_program,
            )
            pass

    async def update_schedule_test(self, result, time):
        """Test function to do. Update schedule from Bosch gateway."""
        self._time = time
        self._switch_points = result.get(self._switchpoints_key)

    @property
    def setpoints(self):
        """Retrieve json setpoints."""
        return self._setpoints_temp

    @property
    def time(self):
        """Get current time of Gateway."""
        return self._time

    @property
    def active_program(self):
        """Get active program."""
        return self._active_program

    def cache_temp_for_mode(self, temp):
        """Save active program for cache."""
        active_setpoint = self._op_mode.current_mode
        if self._op_mode.is_auto:
            active_setpoint = self.get_temp_in_schedule()[MODE]
        if active_setpoint in self._setpoints_temp:
            self._setpoints_temp[active_setpoint][VALUE] = temp

    async def _get_setpoint_temp(self, setpoint_property, setpoint):
        """Download temp for setpoint."""
        uri = f"{setpoint_property[ID]}/{setpoint}"
        _LOGGER.debug("Getting setpoint for URI %s", uri)
        try:
            result = await self._connector.get(uri)
            if self._bus_type == CAN and result.get(VALUE, 0) == 1:
                uri = f"/{self._circuit_type}/{self._circuit_name}/currentSetpoint"
                result = await self._connector.get(uri)
        except DeviceException as err:
            if setpoint == ON and self._bus_type != CAN:
                setpoint = "high"
                result = await self._connector.get(
                    f"{setpoint_property[ID]}/{setpoint}"
                )
            if setpoint == OFF:
                result = {}
                pass
            else:
                _LOGGER.debug("Bug %s", err)
                raise DeviceException
        return {
            MODE: setpoint,
            VALUE: result.get(VALUE, 0),
            MAX: result.get(MAX_VALUE, 0),
            MIN: result.get(MIN_VALUE, 0),
            URI: uri,
        }

    async def _parse_schedule(self, switch_points, setpoint_property):
        """Convert Bosch schedule to dict format."""
        if not setpoint_property:
            setpoint_property = {
                ID: f"/{self._circuit_type}/{self._circuit_name}/temperatureLevels"
            }
        for switch in switch_points:
            setpoint = switch[self._schedule_def_db.get(K_SETPOINT)]
            if (
                setpoint not in self._setpoints_temp
                and self._switchprogram_mode == LEVELS
            ):
                self._setpoints_temp[setpoint] = await self._get_setpoint_temp(
                    setpoint_property, setpoint
                )
        self._switch_points = switch_points

    def get_temp_for_current_mode(self):
        """This is working only in manual for RC35 where op_mode == setpoint."""
        cache = {}
        # self._mode_to_setpoint.get(self._active_program, {}).get()
        if self._op_mode.is_manual:
            return self._setpoints_temp.get(self._op_mode.current_mode, {}).get(
                VALUE, -1
            )
        if not self._schedule_found:
            return ACTIVE_PROGRAM
        if self.time:
            cache = self.get_temp_in_schedule()
        return cache.get(TEMP, 0)

    def get_max_temp_for_mode(self, extra_val=False):
        """Get max temp for mode in schedule."""
        return self.get_min_max_for_mode(MAX, extra_val)

    def get_min_temp_for_mode(self, extra_val=False):
        """Get min temp for mode in schedule."""
        val = self.get_min_max_for_mode(MIN, extra_val)
        return val

    def get_min_max_for_mode(self, min_max, extra_val=False):
        cache = {}
        extra_val = extra_val if extra_val else -1 if self._op_mode.is_manual else 0
        if self._op_mode.is_manual:
            return self._setpoints_temp.get(self._op_mode.current_mode, {}).get(
                min_max, extra_val
            )
        if not self._schedule_found:
            return ACTIVE_PROGRAM
        if self.time:
            cache = self.get_temp_in_schedule()
        if (
            min_max == MAX
            and cache.get(VALUE, 0) > cache.get(min_max, 0)
            or cache.get(VALUE, 0) < cache.get(MIN, 0)
        ):
            return extra_val
        return cache.get(min_max, extra_val)

    def get_setpoint_for_current_mode(self):
        """Get setpoints for mode."""
        cache = {}
        if self._op_mode.is_manual:
            return self._setpoints_temp.get(self._op_mode.current_mode, {}).get(
                MODE, -1
            )
        if not self._schedule_found:
            return ACTIVE_PROGRAM
        if self.time:
            cache = self.get_temp_in_schedule()
            if self._bus_type == CAN and cache.get(MODE) == ON:
                return "currentSetpoint"
        return cache.get(MODE)

    def get_uri_setpoint_for_current_mode(self):
        """Get setpoints for mode."""
        cache = {}
        if self._op_mode.is_manual:
            return self._setpoints_temp.get(self._op_mode.current_mode, {}).get(URI, -1)
        if not self._schedule_found:
            return ACTIVE_PROGRAM
        if self.time:
            cache = self.get_temp_in_schedule()
        return cache.get(URI)

    def get_temp_in_schedule(self):
        """Find temp in schedule for current date."""

        def sort_switchpoints(switchpoints):
            day = switchpoints[self._day_key]
            return (DAYS_INT.index(day), switchpoints[self._time_key])

        if self._time:
            try:
                bosch_date = datetime.strptime(self._time[0:25], self._date_format)
            except ValueError as err:
                if self._date_format != _CT200_DATE_FORMAT:
                    raise
                try:
                    bosch_date = datetime.strptime(
                        self._time, _CT200_NAIVE_DATE_FORMAT
                    )
                except ValueError:
                    raise err
                if bosch_date.strftime(_CT200_NAIVE_DATE_FORMAT) != self._time:
                    raise err
            day_of_week = DAYS_INT[bosch_date.weekday()]
            if self._switch_points:
                switch_points = self._switch_points.copy()
                current_setpoint = {
                    self._day_key: day_of_week,
                    self._setpoint_key: "",
                    self._time_key: self._get_minutes_since_midnight(bosch_date),
                }
                switch_points.append(current_setpoint)
                switch_points.sort(key=sort_switchpoints)
                _prev_setpoint = switch_points[
                    switch_points.index(current_setpoint) - 1
                ][self._setpoint_key]
                if self._switchprogram_mode == LEVELS:
                    return {
                        MODE: _prev_setpoint,
                        TEMP: self._setpoints_temp[_prev_setpoint][VALUE],
                        MAX: self._setpoints_temp[_prev_setpoint][MAX],
                        MIN: self._setpoints_temp[_prev_setpoint][MIN],
                        URI: self._setpoints_temp[_prev_setpoint][URI],
                    }
                elif self._switchprogram_mode == ABSOLUTE:
                    return {
                        MODE: ABSOLUTE,
                        TEMP: float(_prev_setpoint),
                        MAX: DEFAULT_MAX_HC_TEMP,
                        MIN: DEFAULT_MIN_HC_TEMP,
                        URI: None,
                    }
        return {}

    def _get_minutes_since_midnight(self, date):
        """Retrieve minutes since midnight."""
        return int(
            (
                date - date.replace(hour=0, minute=0, second=0, microsecond=0)
            ).total_seconds()
            / 60.0
        )


__all__ = ["Schedule", "ZonePrograms"]
