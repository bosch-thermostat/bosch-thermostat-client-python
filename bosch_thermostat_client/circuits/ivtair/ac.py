"""Air Conditioning Circuit for PoinTT API."""

import logging
from ..circuit import BasicCircuit
from bosch_thermostat_client.const import (
    VALUE,
    URI,
    RESULT,
    HVAC_COOL,
    HVAC_HEAT,
    HVAC_FAN,
    HVAC_OFF,
)

_LOGGER = logging.getLogger(__name__)


class ACCircuit(BasicCircuit):
    """Air Conditioning circuit for PoinTT API devices."""

    # Override allowed types to include all AC property types
    # PoinTT API uses "regular", "operation_mode", and "setpoint" types
    _allowed_types = ("regular", "binary", "operation_mode", "setpoint", "number")

    # AC-specific operation modes
    AC_MODE_AUTO = "auto"
    AC_MODE_HEAT = "heat"
    AC_MODE_COOL = "cool"
    AC_MODE_FAN = "fanOnly"

    # Fan speeds
    FAN_AUTO = "auto"
    FAN_QUIET = "quiet"
    FAN_LOW = "low"
    FAN_MID = "mid"
    FAN_HIGH = "high"

    # Air flow directions
    AIRFLOW_H_CENTER = "center"
    AIRFLOW_H_LEFT = "left"
    AIRFLOW_H_RIGHT = "right"
    AIRFLOW_H_SWING = "swing"

    AIRFLOW_V_AUTO = "auto"
    AIRFLOW_V_ANGLE1 = "angle1"
    AIRFLOW_V_ANGLE2 = "angle2"
    AIRFLOW_V_ANGLE3 = "angle3"
    AIRFLOW_V_ANGLE4 = "angle4"
    AIRFLOW_V_ANGLE5 = "angle5"
    AIRFLOW_V_SWING = "swing"

    def __init__(self, connector, attr_id, db, _type, bus_type, **kwargs):
        """Initialize AC circuit.

        PoinTT API uses absolute paths in refs, not relative paths like other circuits.
        We need to override the URI construction from BasicCircuit to use the ref IDs directly.
        """
        # Call parent init but we'll override the _data URIs
        super().__init__(connector, attr_id, db, _type, bus_type, **kwargs)

        # Override URIs from BasicCircuit - PoinTT uses absolute paths
        # BasicCircuit constructs: uri = f"{self._main_uri}/{value[ID]}"
        # But PoinTT refs already have the full path in ID
        from bosch_thermostat_client.const import REFS, ID, URI, TYPE, RESULT
        if REFS in self._db:
            for key, value in self._db[REFS].items():
                # Use the ID directly as URI (it's already absolute for PoinTT)
                self._data[key] = {RESULT: {}, URI: value[ID], TYPE: value[TYPE]}

    async def initialize(self):
        """Initialize AC circuit.

        PoinTT API doesn't have individual circuit endpoints - all data comes from
        the bulk endpoint. We just mark the circuit as active and initialize switches.
        """
        _LOGGER.debug("ACCircuit.initialize() called")
        # Mark circuit as active (no STATUS endpoint to fetch)
        self._state = True
        _LOGGER.debug("ACCircuit state set to True")

        # Initialize switches if database has them
        from bosch_thermostat_client.const import SWITCHES
        switches_data = self._db.get(SWITCHES)
        _LOGGER.debug(f"Switches data from DB: {switches_data is not None and len(switches_data) if switches_data else 0} switches")

        try:
            await self._switches.initialize(switches=switches_data)
            _LOGGER.debug("Switches initialized successfully")
        except Exception as e:
            _LOGGER.error(f"Failed to initialize switches: {e}", exc_info=True)
            # Don't let switch initialization failure prevent circuit from working
            pass

    @property
    def target_temperature(self):
        """Get target temperature setpoint."""
        return self.get_value("target_temp")

    @property
    def operation_mode(self):
        """Get current operation mode."""
        return self.get_value("operation_mode")

    @property
    def is_on(self):
        """Check if AC is turned on."""
        ac_control = self.get_value("status")  # status ref maps to acControl
        return ac_control == "on"

    @property
    def hvac_action(self):
        """Get current HVAC action based on operation mode and state."""
        if not self.is_on:
            return HVAC_OFF

        mode = self.operation_mode
        if mode == self.AC_MODE_HEAT:
            return HVAC_HEAT
        elif mode == self.AC_MODE_COOL:
            return HVAC_COOL
        elif mode == self.AC_MODE_FAN:
            return HVAC_FAN
        elif mode == self.AC_MODE_AUTO:
            # In auto mode, determine action based on current vs target temp
            current = self.current_temp
            target = self.target_temperature
            if current and target:
                if current < target:
                    return HVAC_HEAT
                elif current > target:
                    return HVAC_COOL
                else:
                    return HVAC_FAN
        return HVAC_OFF

    # ========================================================================
    # Home Assistant Compatibility Properties
    # ========================================================================

    @property
    def temp_units(self):
        """Return temperature units (always Celsius for PoinTT API)."""
        return "C"

    @property
    def support_presets(self):
        """Return whether presets are supported (not for AC)."""
        return False

    @property
    def min_temp(self):
        """Return minimum temperature for AC (16.0°C for PoinTT API)."""
        return 16.0

    @property
    def max_temp(self):
        """Return maximum temperature for AC (30.0°C for PoinTT API)."""
        return 30.0

    @property
    def setpoint(self):
        """Return current temperature setpoint.

        For AC, this is the same as target_temperature.
        Required by HA's BoschThermostat for state_attributes.
        """
        return self.target_temperature

    @property
    def schedule(self):
        """Return schedule object (not supported for AC).

        AC units via PoinTT API don't support schedules.
        Required by HA's BoschThermostat for state_attributes.
        """
        return None

    @property
    def extra_state_attributes(self):
        """Return extra state attributes for HA.

        Optional property for additional state information.
        """
        return {}

    @property
    def ha_modes(self):
        """Return list of available HVAC modes for Home Assistant.

        Maps AC operation modes to HA climate HVAC modes:
        - auto -> auto
        - heat -> heat
        - cool -> cool
        - fanOnly -> fan_only
        - off (via status) -> off
        """
        modes = ["off"]  # Always support turning off

        # Add modes based on available AC operation modes
        # For now, assume all modes are available since PoinTT API doesn't
        # expose capability discovery for operation modes
        modes.extend(["auto", "heat", "cool", "fan_only"])

        return modes

    @property
    def ha_mode(self):
        """Return current HVAC mode in Home Assistant terminology.

        Maps Bosch AC operation modes to HA HVAC modes:
        - "auto" -> "auto"
        - "heat" -> "heat"
        - "cool" -> "cool"
        - "fanOnly" -> "fan_only"
        - status=="off" -> "off"
        """
        if not self.is_on:
            return "off"

        mode = self.operation_mode
        if mode == self.AC_MODE_AUTO:
            return "auto"
        elif mode == self.AC_MODE_HEAT:
            return "heat"
        elif mode == self.AC_MODE_COOL:
            return "cool"
        elif mode == self.AC_MODE_FAN:
            return "fan_only"

        # Default to off if mode is unknown
        return "off"

    async def set_ha_mode(self, hvac_mode):
        """Set HVAC mode using Home Assistant terminology.

        Args:
            hvac_mode: HA HVAC mode ("auto", "heat", "cool", "fan_only", "off")

        Returns:
            int: 1 if mode changed, 0 if no change, -1 if error
        """
        _LOGGER.debug(f"Setting HA mode to {hvac_mode}")

        # Handle off mode - turn off the AC
        if hvac_mode == "off":
            result = await self.turn_off()
            return 1 if result else -1

        # Map HA mode to AC operation mode
        mode_map = {
            "auto": self.AC_MODE_AUTO,
            "heat": self.AC_MODE_HEAT,
            "cool": self.AC_MODE_COOL,
            "fan_only": self.AC_MODE_FAN,
        }

        ac_mode = mode_map.get(hvac_mode)
        if not ac_mode:
            _LOGGER.error(f"Invalid HA HVAC mode: {hvac_mode}")
            return -1

        # Check if mode is changing
        current_mode = self.operation_mode
        if current_mode == ac_mode and self.is_on:
            _LOGGER.debug("Mode unchanged")
            return 0

        # Turn on if needed (set_operation_mode requires AC to be on)
        if not self.is_on:
            await self.turn_on()

        # Set the operation mode
        result = await self.set_operation_mode(ac_mode)

        return 1 if result else -1

    @property
    def available_operation_modes(self):
        """Get available operation modes."""
        return [self.AC_MODE_AUTO, self.AC_MODE_HEAT, self.AC_MODE_COOL, self.AC_MODE_FAN]

    @property
    def available_fan_speeds(self):
        """Get available fan speeds."""
        return [self.FAN_AUTO, self.FAN_QUIET, self.FAN_LOW, self.FAN_MID, self.FAN_HIGH]

    @property
    def available_horizontal_airflows(self):
        """Get available horizontal air flow directions."""
        return [self.AIRFLOW_H_CENTER, self.AIRFLOW_H_LEFT, self.AIRFLOW_H_RIGHT, self.AIRFLOW_H_SWING]

    @property
    def available_vertical_airflows(self):
        """Get available vertical air flow directions."""
        return [self.AIRFLOW_V_AUTO, self.AIRFLOW_V_ANGLE1, self.AIRFLOW_V_ANGLE2,
                self.AIRFLOW_V_ANGLE3, self.AIRFLOW_V_ANGLE4, self.AIRFLOW_V_ANGLE5,
                self.AIRFLOW_V_SWING]

    async def set_temperature(self, temperature):
        """Set target temperature."""
        if not isinstance(temperature, (int, float)):
            _LOGGER.error("Temperature must be a number")
            return False

        # PoinTT API temperature range is 16.0 - 30.0°C
        if not (16.0 <= temperature <= 30.0):
            _LOGGER.error("Temperature must be between 16.0 and 30.0°C")
            return False

        try:
            uri = self._data["target_temp"][URI]
            result = await self._connector.put(uri, temperature)
            if result:
                _LOGGER.debug("Set temperature to %s°C", temperature)
                return True
            return False
        except Exception as e:
            _LOGGER.error("Failed to set temperature: %s", e)
            return False

    async def set_operation_mode(self, mode):
        """Set operation mode (auto, heat, cool, fanOnly)."""
        if mode not in self.available_operation_modes:
            _LOGGER.error("Invalid operation mode: %s", mode)
            return False

        try:
            uri = self._data["operation_mode"][URI]
            result = await self._connector.put(uri, mode)
            if result:
                _LOGGER.debug("Set operation mode to %s", mode)
                return True
            return False
        except Exception as e:
            _LOGGER.error("Failed to set operation mode: %s", e)
            return False

    async def set_fan_speed(self, speed):
        """Set fan speed (auto, quiet, low, mid, high)."""
        if speed not in self.available_fan_speeds:
            _LOGGER.error("Invalid fan speed: %s", speed)
            return False

        try:
            uri = self._data["fan_speed"][URI]
            result = await self._connector.put(uri, speed)
            if result:
                _LOGGER.debug("Set fan speed to %s", speed)
                return True
            return False
        except Exception as e:
            _LOGGER.error("Failed to set fan speed: %s", e)
            return False

    async def set_air_flow_horizontal(self, direction):
        """Set horizontal air flow direction."""
        if direction not in self.available_horizontal_airflows:
            _LOGGER.error("Invalid horizontal air flow direction: %s", direction)
            return False

        try:
            uri = self._data["air_flow_horizontal"][URI]
            result = await self._connector.put(uri, direction)
            if result:
                _LOGGER.debug("Set horizontal air flow to %s", direction)
                return True
            return False
        except Exception as e:
            _LOGGER.error("Failed to set horizontal air flow: %s", e)
            return False

    async def set_air_flow_vertical(self, direction):
        """Set vertical air flow direction."""
        if direction not in self.available_vertical_airflows:
            _LOGGER.error("Invalid vertical air flow direction: %s", direction)
            return False

        try:
            uri = self._data["air_flow_vertical"][URI]
            result = await self._connector.put(uri, direction)
            if result:
                _LOGGER.debug("Set vertical air flow to %s", direction)
                return True
            return False
        except Exception as e:
            _LOGGER.error("Failed to set vertical air flow: %s", e)
            return False

    async def turn_on(self):
        """Turn the AC on."""
        try:
            uri = self._data["status"][URI]
            result = await self._connector.put(uri, "on")
            if result:
                _LOGGER.debug("Turned AC on")
                return True
            return False
        except Exception as e:
            _LOGGER.error("Failed to turn AC on: %s", e)
            return False

    async def turn_off(self):
        """Turn the AC off."""
        try:
            uri = self._data["status"][URI]
            result = await self._connector.put(uri, "off")
            if result:
                _LOGGER.debug("Turned AC off")
                return True
            return False
        except Exception as e:
            _LOGGER.error("Failed to turn AC off: %s", e)
            return False
