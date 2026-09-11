"""Main circuit object."""
from __future__ import annotations
from bosch_thermostat_client.switches import Switches
from bosch_thermostat_client.schedule import Schedule
import logging
from bosch_thermostat_client.const import (
    ID,
    CURRENT_TEMP,
    OPERATION_MODE,
    REFS,
    REFERENCES,
    HA_STATES,
    STATUS,
    TYPE,
    URI,
    RESULT,
    OFF,
    ACTIVE_PROGRAM,
    MODE_TO_SETPOINT,
    UNITS,
    BOSCH_NAME,
    HA_NAME,
    SENSORS,
    SWITCHES,
    SWITCH_PROGRAMS,
    VALUE,
    MAX_VALUE,
    MIN_VALUE,
    DEFAULT_MAX_TEMP,
    DEFAULT_MIN_TEMP,
)
from bosch_thermostat_client.helper import BoschSingleEntity
from bosch_thermostat_client.exceptions import DeviceConnectionError, DeviceException
from bosch_thermostat_client.sensors import Sensors

from bosch_thermostat_client.operation_mode import OperationModeHelper

_LOGGER = logging.getLogger(__name__)


class BasicCircuit(BoschSingleEntity):
    def __init__(self, connector, attr_id, db, _type, bus_type, **kwargs):
        """Basic circuit init."""
        name = attr_id.split("/").pop()
        self._db = db[_type]
        self._bus_type = bus_type
        super().__init__(name=name, connector=connector, attr_id=attr_id)
        self._main_uri = f"/{_type}/{self.name}"
        self._operation_mode = {}
        if REFS in self._db:
            for key, value in self._db[REFS].items():
                uri = f"{self._main_uri}/{value[ID]}"
                self._data[key] = {RESULT: {}, URI: uri, TYPE: value[TYPE]}
        self._sensors = Sensors(
            connector=connector,
            sensors_db=self._db.get(SENSORS, {}),
            uri_prefix=self._main_uri,
            data=self._data,
            parent=self,
        )
        self._switches = Switches(
            connector=connector,
            uri_prefix=self._main_uri,
            parent=self,
        )

    @property
    def db_json(self):
        """Give simple json scheme of circuit."""
        return self._db

    async def update_requested_key(self, key, *, strict_connection=False):
        """Update info about Circuit asynchronously."""
        if key in self._data:
            try:
                result = await self._connector.get(self._data[key][URI])
                self.process_results(result, key)
                self._state = True
            except DeviceException as err:
                if strict_connection and isinstance(err, DeviceConnectionError):
                    raise
                self._state = False

    @property
    def state(self):
        return self._state

    @property
    def sensors(self):
        return self._sensors

    @property
    def regular_switches(self):
        return self._switches

    @property
    def number_switches(self):
        return self._switches.number_switches

    async def initialize(self):
        """Check each uri if return json with values."""
        await self.update_requested_key(STATUS, strict_connection=True)
        await self._switches.initialize(switches=self._db.get(SWITCHES))

    @property
    def id(self):
        """Get ID of circuit. Name might be overriden by eg Zone name, so id is always last part of URI."""
        return super().name


class Circuit(BasicCircuit):
    """Parent object for circuit of type HC or DHW."""

    _omit_updates = []

    def __init__(self, connector, attr_id, db, _type, bus_type, current_date=None):
        """Initialize circuit with get, put and id from gateway."""
        super().__init__(connector, attr_id, db, _type, bus_type)
        if not hasattr(self, "_op_mode"):
            self._op_mode = OperationModeHelper(
                self.name, self._db.get(MODE_TO_SETPOINT)
            )
        self._target_temp = 0

    @property
    def support_target_temp(self):
        return True

    @property
    def schedule(self):
        """Retrieve schedule of HC/DHW."""
        raise NotImplementedError

    @property
    def _hastates(self):
        """Get dictionary which converts Bosch states to HA States."""
        return self._db.get(HA_STATES, None)

    @property
    def setpoint(self):
        raise NotImplementedError

    async def set_service_call(self, uri, value):
        """WARNING! It doesn't check if value you send is good!."""
        _LOGGER.info(f"Sending service call {uri} with {value}")
        uri = f"{self._main_uri}/{uri}"
        val = await self._connector.put(uri, value)
        return val

    async def set_operation_mode(self, new_mode):
        """Set operation_mode of Heating Circuit."""
        if self._op_mode.current_mode == new_mode:
            _LOGGER.warning("Trying to set mode which is already set %s", new_mode)
            return None
        if new_mode in self._op_mode.available_modes:
            await self._connector.put(self._op_mode.uri, new_mode)
            self._op_mode.set_new_operation_mode(new_mode)
            return new_mode
        _LOGGER.warning(
            "You wanted to set %s, but it is not allowed %s",
            new_mode,
            self._op_mode.available_modes,
        )

    def _find_ha_mode(self, ha_mode):
        for v in self._hastates:
            if v[HA_NAME] == ha_mode:
                return v[BOSCH_NAME]

    @property
    def _temp_setpoint(self):
        return self._op_mode.temp_setpoint()

    @property
    def support_presets(self):
        return False

    @property
    def hvac_action(self):
        return None
    
    @property
    def extra_state_attributes(self) -> dict:
        return {}

    async def update_temp_after_ha_mode(self, old_setpoint, new_mode, old_mode) -> int:
        """Helper to fetch new temp. attribute if operation mode was changed."""
        different_mode = new_mode != old_mode
        try:
            if (
                different_mode
                and old_setpoint != self._temp_setpoint
                and self._op_mode.is_manual
            ):
                temp = self.get_value(self._temp_setpoint, 0)
                if temp == 0:
                    result = await self._connector.get(
                        self._data[self._temp_setpoint][URI]
                    )
                    self.process_results(result, self._temp_setpoint)
        except DeviceException as err:
            _LOGGER.debug(f"Can't update data for mode {new_mode}. Error: {err}")
            pass
        if different_mode:
            return 1
        return 0

    async def set_ha_mode(self, ha_mode):
        """Helper to set operation mode."""
        old_setpoint = self._temp_setpoint
        old_mode = self._op_mode.current_mode
        bosch_mode = self._op_mode.find_in_available_modes(self._find_ha_mode(ha_mode))
        new_mode = await self.set_operation_mode(bosch_mode)
        return await self.update_temp_after_ha_mode(old_setpoint, new_mode, old_mode)

    @property
    def current_temp(self):
        """Give current temperature of circuit."""
        temp = self.get_value(CURRENT_TEMP)
        if temp:
            _LOGGER.debug(
                "Current temp of %s is %s",
                self.name.upper(),
                self.get_property(CURRENT_TEMP),
            )
            temp = float(temp)
            if temp > 0 and temp < 120:
                return temp

    @property
    def temp_units(self):
        """Return units of temperature."""
        return self.get_property(CURRENT_TEMP).get(UNITS)

    @property
    def ha_modes(self):
        """Retrieve HA modes."""
        raise NotImplementedError

    @property
    def ha_mode(self):
        """Retrieve current mode in HA terminology."""
        for v in self._hastates:
            for x in v[BOSCH_NAME]:
                if x == self._op_mode.current_mode:
                    return v[HA_NAME]
        return OFF

    def get_activeswitchprogram(self):
        """
        Retrieve active program from thermostat.
        If ActiveSwitch program is not present
        then take first one from the list from result.
        """
        active_program = self.get_value(ACTIVE_PROGRAM)
        if active_program:
            return active_program
        try:
            result = self.get_property(SWITCH_PROGRAMS)
            return result[REFERENCES][0][ID].split("/")[-1]
        except (IndexError, KeyError) as err:
            _LOGGER.debug("Error getting data from result %s. Result  %s", err, result)
            return None

    @property
    def target_temperature(self):
        """Get target temperature of Circuit. Temporary or Room set point."""
        raise NotImplementedError

    @property
    def min_temp(self):
        """Retrieve minimum temperature."""
        raise NotImplementedError

    @property
    def max_temp(self):
        """Retrieve maximum temperature."""
        raise NotImplementedError

    async def set_temperature(self, temperature):
        """Set temperature of Circuit."""
        raise NotImplementedError

    async def update(self):
        """Update info about Circuit asynchronously."""
        _LOGGER.debug("Updating circuit %s", self.name)
        last_item = list(self._data.keys())[-1]

        async def fetch_data(key) -> dict | None:
            try:
                result = await self._connector.get(item[URI])
                self.process_results(result, key)
                return result
            except DeviceException:
                pass
            return None

        for key, item in self._data.items():
            if not (self._omit_updates and key in self._omit_updates):
                result = await fetch_data(key)
                is_operation_type = item[TYPE] == OPERATION_MODE
                if is_operation_type and result:
                    op_mode = self.process_results(result, key, True)
                    if not self._op_mode.is_set:
                        self._op_mode.init_op_mode(op_mode, item[URI])
                    else:
                        self._op_mode.set_new_operation_mode(op_mode[VALUE])

            if key == last_item:
                self._state = True

    @property
    def support_charge(self):
        """Is DHW support charge."""
        return True


class CircuitWithSchedule(Circuit):
    def __init__(
        self, connector, attr_id, db, _type, bus_type, current_date=None, **kwargs
    ):
        super().__init__(
            connector=connector,
            attr_id=attr_id,
            db=db,
            _type=_type,
            bus_type=bus_type,
            current_date=current_date,
        )
        self._schedule = Schedule(
            connector=connector,
            circuit_type=_type,
            circuit_name=self.name,
            current_time=current_date,
            bus_type=bus_type,
            db=self._db,
            op_mode=self._op_mode,
            date_format=db.get("date_format", "%Y-%m-%dT%H:%M:%S"),
        )

    @property
    def schedule(self):
        """Retrieve schedule of HC/DHW."""
        return self._schedule or None

    @property
    def setpoint(self):
        """
        Retrieve setpoint in which is currently Circuit.
        Might be equal to operation_mode, might me taken from schedule.
        """
        if self._op_mode.is_off:
            return OFF
        if self._op_mode.is_manual:
            return self._op_mode.current_mode
        if self._schedule:
            found_setpoint = self._schedule.get_setpoint_for_current_mode()
            if found_setpoint == ACTIVE_PROGRAM:
                found_setpoint = self._schedule.active_program
            return found_setpoint

    @property
    def target_temperature(self):
        """Get target temperature of Circtuit. Temporary or Room set point."""
        if self._op_mode.is_off:
            self._target_temp = 0
            return self._target_temp
        if self._temp_setpoint:
            target_temp = self.get_value(self._temp_setpoint, 0)
            if target_temp > 0:
                self._target_temp = target_temp
                return self._target_temp
        target_temp = self.schedule.get_temp_for_current_mode()
        if target_temp == ACTIVE_PROGRAM:
            target_temp = self.get_value_from_active_setpoint(VALUE)
        if target_temp >= 0:
            self._target_temp = target_temp
        return self._target_temp

    @property
    def active_program_setpoint(self):
        return self._op_mode.temp_setpoint(self.schedule.active_program)

    def get_value_from_active_setpoint(self, prop_name):
        activeSetpointValue = self.get_property(self.active_program_setpoint)
        default = 0
        if prop_name == MIN_VALUE:
            default = DEFAULT_MIN_TEMP
        elif prop_name == MAX_VALUE:
            default = DEFAULT_MAX_TEMP
        return activeSetpointValue.get(prop_name, default)

    async def update(self):
        """Update info about Circuit asynchronously."""
        await super().update()
        active_program = self.get_activeswitchprogram()
        if active_program:
            await self._schedule.update_schedule(active_program)
