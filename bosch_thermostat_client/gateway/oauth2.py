"""Gateway module connecting to Bosch thermostat via PoinTT API."""

import json
import logging

from bosch_thermostat_client.connectors import connector_ivt_chooser
from bosch_thermostat_client.const import (
    GATEWAY,
    HC,
    AC,
    MODELS,
    OAUTH2,
    SENSORS,
    VALUE,
    VALUES,
    FIRMWARE_VERSION,
    TYPE,
    ID,
    REFERENCES,
    SYSTEM_BUS,
    UUID,
)
from bosch_thermostat_client.const.ivt import SYSTEM_INFO
from bosch_thermostat_client.const.easycontrol import CIRCUIT_TYPES as EASYCONTROL_CIRCUIT_TYPES
from bosch_thermostat_client.const.oauth2 import CIRCUIT_TYPES as OAUTH2_CIRCUIT_TYPES, SYSTEM_MODEL
from bosch_thermostat_client.exceptions import DeviceException, FirmwareException, UnknownDevice
from bosch_thermostat_client.db import get_db_of_firmware, async_get_errors
from bosch_thermostat_client.circuits import Circuits
from bosch_thermostat_client.circuits.circuits import choose_circuit_type

from .base import BaseGateway

_LOGGER = logging.getLogger(__name__)


class Oauth2Gateway(BaseGateway):
    """Gateway connecting to the Bosch PoinTT API."""

    def __init__(
        self,
        session,
        device_type,
        session_type=None,
        host=None,
        access_key=None,
        access_token=None,
        refresh_token=None,
        token_expires_at=None,
        token_file=None,
        **kwargs
    ):
        """OAuth2 Gateway constructor

        Args:
            session: aiohttp session for HTTP requests (required for OAuth2)
            session_type (str, optional): Protocol type (accepted for compatibility, ignored - always HTTP)
            device_type (str, optional): Device type for database loading (e.g., "IVT", "NEFIT", "EASYCONTROL")
            host (str): Device ID for the OAuth2 API
            access_key (optional): Not used for OAuth (accepted for compatibility with HA)
            access_token (str): OAuth access token
            refresh_token (str, optional): OAuth refresh token for token renewal
            token_expires_at (str, optional): ISO format timestamp when token expires
            token_file (str, optional): Path to token storage file (for standalone use, not HA)
            **kwargs: Additional arguments for compatibility
        """
        from bosch_thermostat_client.const.easycontrol import EASYCONTROL
        if device_type == EASYCONTROL:
            self.circuit_types = EASYCONTROL_CIRCUIT_TYPES
        else:
            self.circuit_types = OAUTH2_CIRCUIT_TYPES

        self._device_id = host  # For OAuth2 API, host is the device ID
        self._access_token = access_token
        self._refresh_token = refresh_token
        self.device_type = device_type

        # Use the connector chooser to get the right connector
        Connector = connector_ivt_chooser(OAUTH2)
        self._connector = Connector(
            host=host,  # Device ID
            access_token=access_token,
            device_type=device_type,
            refresh_token=refresh_token,
            token_expires_at=token_expires_at,
            loop=session,
            token_file=token_file,
        )
        self._data = {GATEWAY: {}}
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
        self._bus_type = system_bus
        system_info = self._data[GATEWAY].get(SYSTEM_INFO)
        attached_devices = {}
        if system_info:
            for info in system_info:
                _id = info.get("ModuleHwIdentStr", -1)
                model = model_scheme.get(_id)
                if model is not None:
                    _LOGGER.debug("Found supported device %s with id %s", model, _id)
                    attached_devices[_id] = model
            if attached_devices:
                found_model = attached_devices[sorted(attached_devices.keys())[-1]]
                _LOGGER.debug("Using model %s as database schema", found_model[VALUE])
                return found_model
        sys_model = self._data[GATEWAY].get(SYSTEM_MODEL)
        if sys_model:
            model = model_scheme.get(sys_model)
            if model is not None:
                _LOGGER.debug("Found supported device %s", model)
                return model
        # POINTT API: productID is the reliable identifier for EasyControl devices
        product_id = self._data[GATEWAY].get("productID")
        if product_id:
            model = model_scheme.get(product_id)
            if model is not None:
                _LOGGER.debug("Found supported device via productID %s: %s", product_id, model)
                return model

        raise UnknownDevice(
            "Cannot find supported device. system_info=%s, productID=%s"
            % (json.dumps(system_info), product_id)
        )

    async def initialize_circuits(self, circ_type):
        """Initialize circuits for PoinTT API.

        PoinTT API doesn't expose circuit discovery endpoints. We create the single
        AC circuit directly instead of using the crawl() discovery mechanism.
        """
        if circ_type == AC:
            # Create Circuits container
            self._data[circ_type] = Circuits(
                self._connector,
                circ_type,
                self._bus_type,
                self.device_type
            )

            # Create static circuit data for the single AC unit
            # This replaces the need for /acCircuits and /ac1 endpoints
            circuit_id = "ac1"

            # Get the circuit class for AC + POINTTAPI
            CircuitClass = choose_circuit_type(self.device_type, circ_type)

            # Create the AC circuit directly
            # Note: _type should be the database key (e.g., "acCircuits"), not the const (e.g., "ac")
            try:
                circuit_object = CircuitClass(
                    connector=self._connector,
                    attr_id=circuit_id,
                    db=self._db,
                    _type=CIRCUIT_TYPES[circ_type],  # Maps AC -> "acCircuits"
                    bus_type=self._bus_type,
                )
                _LOGGER.debug(f"Created AC circuit object: {circuit_object}")
            except Exception as e:
                _LOGGER.error(f"Failed to create AC circuit object: {e}", exc_info=True)
                return []

            if circuit_object:
                try:
                    await circuit_object.initialize()
                    _LOGGER.debug(f"AC circuit initialized, state={circuit_object.state}")
                except Exception as e:
                    _LOGGER.error(f"Failed to initialize AC circuit: {e}", exc_info=True)
                    return []

                if circuit_object.state:
                    self._data[circ_type]._items.append(circuit_object)
                    _LOGGER.info("Successfully initialized AC circuit: ac1")
                else:
                    _LOGGER.warning("AC circuit ac1 failed to initialize (state=False)")
            else:
                _LOGGER.warning("Failed to create AC circuit object")

            # Return the list of circuits for get_capabilities() to detect
            return self.get_circuits(circ_type)

        else:
            # For other circuit types (HC, DHW, etc.), use standard discovery
            return await super().initialize_circuits(circ_type)

    @property
    def ac_circuits(self):
        """Get AC circuit list."""
        if AC in self._data and self._data[AC]:
            return self._data[AC].circuits
        return []

    @property
    def access_token(self):
        """Return current OAuth access token.

        May differ from initial token if refresh occurred.
        Home Assistant should read this after operations and update
        entry.data if it changed.
        """
        return self._connector._access_token

    @property
    def access_key(self):
        """Return None - OAuth doesn't use access_key.

        Provided for compatibility with Home Assistant's standard pattern.
        """
        return None

    @property
    def refresh_token(self):
        """Return current OAuth refresh token.

        Home Assistant should store this in entry.data for persistence.
        """
        return self._connector._refresh_token

    @property
    def token_expires_at(self):
        """Return token expiration timestamp as ISO string.

        Returns:
            str: ISO format timestamp (e.g., "2025-10-30T15:30:00+00:00")
            None: If expiration not set
        """
        if self._connector._token_expires_at:
            return self._connector._token_expires_at.isoformat()
        return None

    def get_token_info(self):
        """Get all token information for HA to store/compare.

        Returns:
            dict: Dictionary with token information:
                - access_token: Current OAuth access token
                - refresh_token: Current OAuth refresh token
                - token_expires_at: ISO string of expiration time
                - device_id: Device ID (for validation)

        Example for HA:
            # Get current tokens
            token_info = gateway.get_token_info()

            # Compare with stored tokens
            if token_info != entry.data.get('token_info'):
                # Update config entry
                hass.config_entries.async_update_entry(
                    entry,
                    data={**entry.data, **token_info}
                )
        """
        return {
            'access_token': self.access_token,
            'refresh_token': self.refresh_token,
            'token_expires_at': self.token_expires_at,
            'device_id': self._device_id,
        }

    def tokens_changed(self, stored_access_token, stored_refresh_token=None):
        """Check if tokens have changed since last storage.

        Useful for HA to determine if config entry needs updating.

        Args:
            stored_access_token: The access token stored in HA config entry
            stored_refresh_token: The refresh token stored in HA config entry (optional)

        Returns:
            bool: True if tokens have changed, False otherwise

        Example for HA:
            # In thermostat_refresh or after any gateway operation
            if gateway.tokens_changed(
                entry.data['access_token'],
                entry.data.get('refresh_token')
            ):
                _LOGGER.info("OAuth tokens refreshed, updating config entry")
                hass.config_entries.async_update_entry(
                    entry,
                    data={
                        **entry.data,
                        'access_token': gateway.access_token,
                        'refresh_token': gateway.refresh_token,
                        'token_expires_at': gateway.token_expires_at,
                    }
                )
        """
        if self.access_token != stored_access_token:
            return True
        if stored_refresh_token and self.refresh_token != stored_refresh_token:
            return True
        return False

    async def check_firmware_validity(self):
        """Check firmware validity.

        PoinTT API doesn't expose firmware version endpoint.
        We hardcode firmware version during initialize(), so if
        the database loaded successfully, firmware is valid.

        Returns:
            bool: Always True for PoinTT API
        """
        return True

    async def check_connection(self):
        """Check connection and return UUID.

        For PoinTT API, the device_id is the unique identifier.
        The API doesn't expose a separate /gateway/uuid endpoint.

        Returns:
            str: Device ID (which serves as the UUID)
        """
        try:
            # Initialize if needed (validates credentials, loads database)
            if not self._initialized:
                await self.initialize()

            # For PoinTT API, device_id IS the UUID
            # Store it in expected location for HA component
            if UUID not in self._data[GATEWAY]:
                self._data[GATEWAY][UUID] = self._device_id

            _LOGGER.debug("PoinTT API connection validated, UUID: %s", self.uuid)

        except Exception as err:
            _LOGGER.error("Failed to check_connection: %s", err)
            raise

        return self.uuid
