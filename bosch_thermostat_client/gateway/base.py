"""Gateway module connecting to Bosch thermostat."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from bosch_thermostat_client.circuits import Circuits
from bosch_thermostat_client.const import (
    BASE_FIRMWARE_VERSION,
    CRAWL_SENSORS,
    DATE,
    DHW,
    DHW_CIRCUITS,
    FIRMWARE_VERSION,
    GATEWAY,
    HC,
    HEATING_CIRCUITS,
    ID,
    MODELS,
    NAME,
    NUMBER,
    RECORDINGS,
    REFS,
    ROOT_PATHS,
    SC,
    SELECT,
    SENSOR,
    SENSORS,
    SWITCH,
    SWITCHES,
    TYPE,
    UUID,
    VALUE,
)
from bosch_thermostat_client.db import (
    async_get_errors,
    get_custom_db,
    get_db_of_firmware,
    get_initial_db,
)
from bosch_thermostat_client.exceptions import (
    DeviceException,
    FirmwareException,
    UnknownDevice,
)
from bosch_thermostat_client.helper import deep_into
from bosch_thermostat_client.sensors import Sensors
from bosch_thermostat_client.switches import Switches

_LOGGER = logging.getLogger(__name__)


class BaseGateway:
    """Base Gateway class."""

    device_type: str
    circuit_types: dict[str, str]

    def __init__(self, host):
        """BaseGateway constructor

        Args:
            host (str): hostname or serial or IP Address
        """
        self._host = host
        self._firmware_version = None
        self._supported_firmware = False
        self._device = None
        self._db = None
        self._initialized = None
        self.initialization_msg = None
        self._bus_type = None
        self._errors = None

    async def get_base_db(self):
        return await get_initial_db(self.device_type)

    async def initialize(self):
        """Initialize gateway asynchronously."""
        initial_db = await self.get_base_db()
        await self._update_info(initial_db.get(GATEWAY))
        self._firmware_version = self._data[GATEWAY].get(FIRMWARE_VERSION)
        self._device = self.get_device_model(initial_db)
        if self._device and VALUE in self._device:
            _LOGGER.debug("Found device %s", json.dumps(self._device))
            self._db = await get_db_of_firmware(
                self._device[TYPE], self._firmware_version
            )
            if self._db:
                _LOGGER.debug(
                    f"Loading database: {self._device[TYPE]} for firmware {self._firmware_version}"
                )
                initial_db.pop(MODELS, None)
                self._db.update(initial_db)
                self._errors = await async_get_errors(self.device_type)
                self._initialized = True
                return
            raise FirmwareException(
                "You might have unsupported firmware version %s"
                % self._firmware_version
            )
        raise UnknownDevice("Your device is unknown %s" % json.dumps(self._device))

    async def custom_initialize(self, extra_db):
        "Custom initialization of component"
        if self._firmware_version:
            self._db = get_custom_db(self._firmware_version, extra_db)
            initial_db = await get_initial_db()
            initial_db.pop(MODELS, None)
            self._db.update(initial_db)
            self._initialized = True

    async def _update_info(self, initial_db):
        raise NotImplementedError

    def get_device_model(self, _db):
        raise NotImplementedError

    @property
    def host(self):
        """Return host of Bosch gateway. Either IP or hostname."""
        return self._host

    @property
    def device_name(self):
        """Device friendly name based on model."""
        if self._device:
            return self._device.get(NAME)

    @property
    def device_model(self):
        if self._device:
            return self._device.get(VALUE, "Unknown")
        return "Unknown"

    @property
    def bus_type(self):
        """Return BUS type detected by lib."""
        return self._bus_type

    def get_items(self, data_type):
        """Get items on types like Sensors, Heating Circuits etc."""
        return self._data[data_type].get_items()

    async def current_date(self):
        """Find current datetime of gateway."""
        try:
            response = await self._connector.get(self._db[GATEWAY].get(DATE))
            date = response.get(VALUE)
        except DeviceException:
            date = datetime.now().strftime(
                self._db.get("date_format", "%Y-%m-%dT%H:%M:%S")
            )
        self._data[GATEWAY][DATE] = date
        return date

    @property
    def database(self):
        """Retrieve db scheme."""
        return self._db

    def set_timeout(self, timeout):
        """Set timeout for API calls."""
        self._connector.set_timeout(timeout)

    @property
    def access_token(self):
        """Return key to store in config entry."""
        return self._access_token

    @property
    def access_key(self):
        """Return original access key to store in config entry. Need to XMPP communication."""
        return self._connector.encryption_key

    @property
    def heating_circuits(self):
        """Get circuit list."""
        return self._data[HC].circuits

    def get_circuits(self, ctype):
        """Get circuit list."""
        return self._data[ctype].circuits if ctype in self._data else []

    @property
    def dhw_circuits(self):
        """Get circuit list."""
        return self._data[DHW].circuits

    @property
    def solar_circuits(self):
        """Get solar circuits."""
        return self._data[SC].circuits

    @property
    def sensors(self) -> list:
        """Get sensors list."""
        if self._data[SENSORS]:
            return self._data[SENSORS].sensors
        return []

    @property
    def switches(self):
        """Get switches class."""
        if SWITCHES in self._data:
            return self._data[SWITCHES]

    @property
    def regular_switches(self):
        """Get switches list."""
        if SWITCHES in self._data:
            return self._data[SWITCHES].switches
        return []

    @property
    def select_switches(self):
        """Get switches list."""
        if SWITCHES in self._data:
            return self._data[SWITCHES].selects

    @property
    def number_switches(self):
        """Get number switches list."""
        if SWITCHES in self._data:
            return self._data[SWITCHES].number_switches
        return []

    @property
    def firmware(self):
        """Get firmware."""
        return self._firmware_version

    @property
    def uuid(self):
        return self.get_info(UUID)

    @property
    def initialized(self):
        return self._initialized

    def get_info(self, key):
        """Get gateway info given key."""
        if key in self._data[GATEWAY]:
            return self._data[GATEWAY][key]
        return None

    async def get_capabilities(self):
        supported = []
        for circuit in self.circuit_types.keys():
            try:
                circuit_object = await self.initialize_circuits(circuit)
                if circuit_object:
                    supported.append(circuit)
                    if circuit_object[0].number_switches:
                        supported.append(NUMBER)
            except DeviceException as err:
                _LOGGER.debug("Circuit %s not found. Skipping it. %s", circuit, err)
                pass
        await self.initialize_sensors()
        await self.initialize_switches()
        supported.append(SWITCH)
        if NUMBER not in supported and self.number_switches:
            supported.append(NUMBER)
        if SELECT not in supported and self.select_switches:
            supported.append(SELECT)
        supported.append(SENSOR)

        return supported

    async def initialize_circuits(self, circ_type):
        """Initialize circuits objects of given type (dhw/hcs)."""
        self._data[circ_type] = Circuits(
            self._connector, circ_type, self._bus_type, self.device_type
        )

        await self._data[circ_type].initialize(
            database=self._db,
            current_date=self.current_date,
            db_prefix=self.circuit_types[circ_type],
        )
        return self.get_circuits(circ_type)

    async def initialize_sensors(self):
        """Initialize sensors objects."""
        if SENSORS in self._db:
            self._data[SENSORS] = Sensors(
                connector=self._connector,
                sensors_db=self._db[SENSORS],
                errors=self._errors,
            )
        if CRAWL_SENSORS in self._db:
            _LOGGER.info("Initializing Crawl Sensors.")
            await self._data[SENSORS].initialize(crawl_sensors=self._db[CRAWL_SENSORS])
        return self.sensors

    async def initialize_switches(self):
        """Initialize switches objects."""
        if SWITCHES in self._db:
            _LOGGER.info("Initializing Switches and Selects.")
            self._data[SWITCHES] = Switches(
                connector=self._connector,
            )
            await self._data[SWITCHES].initialize(switches=self._db[SWITCHES])

    async def rawscan(self):
        """Print out all info from gateway."""
        rawlist = []
        for root in ROOT_PATHS:
            single_scan = await deep_into(root, [], self._connector.get)
            rawlist.append(single_scan if single_scan else {root: "not found"})
        return rawlist

    async def smallscan(self, _type=HC, circuit_number=None):
        """Print out all info from gateway from HC1 or DHW1 only for now."""
        """TODO: add zones support."""
        rawlist = []
        if _type == HC:
            _LOGGER.info("Scanning HC1")
            refs = self._db.get(HEATING_CIRCUITS).get(REFS)
            _main_uri = f"/{self.circuit_types[_type]}/hc{circuit_number if circuit_number else 1}/"
        elif _type == DHW:
            _LOGGER.info("Scanning DHW1")
            refs = self._db.get(DHW_CIRCUITS).get(REFS)
            _main_uri = f"/{self.circuit_types[_type]}/dhw{circuit_number if circuit_number else 1}/"
        elif _type == RECORDINGS:
            _LOGGER.info("Scanning recordings.")
            _main_uri = f"/{RECORDINGS}"
            rawlist.append(await deep_into(_main_uri, [], self._connector.get))
            return rawlist
        else:
            _LOGGER.info("Scanning Sensors.")
            refs = self._db.get(SENSORS)
            _main_uri = ""
        for item in refs.values():
            uri = f"{_main_uri}{item[ID]}"
            _LOGGER.info(f"Scanning {uri}")
            rawlist.append(await deep_into(uri, [], self._connector.get))
        return rawlist

    async def check_connection(self):
        """Check if we are able to connect to Bosch device and return UUID."""
        try:
            if not self._initialized:
                await self.initialize()
            else:
                response = await self._connector.get(self._db[GATEWAY][UUID])
                if VALUE in response:
                    self._data[GATEWAY][UUID] = response[VALUE]
        except DeviceException as err:
            _LOGGER.debug("Failed to check_connection: %s", err)
        return self.uuid

    async def raw_query(self, path):
        """Run RAW query like /gateway/uuid."""
        try:
            return await self._connector.get(path)
        except DeviceException as err:
            _LOGGER.error(err)

    async def raw_put(self, path: str, value: Any) -> None:
        """Run RAW PUT."""
        try:
            return await self._connector.put(path=path, value=value)
        except DeviceException as err:
            _LOGGER.error(err)

    async def close(self, force: bool = False) -> None:
        await self._connector.close(force)

    async def check_firmware_validity(self):
        """Run query against firmware version."""
        fw = await self._connector.get(self._db.get(BASE_FIRMWARE_VERSION))
        if await get_db_of_firmware(self._device[TYPE], fw.get(VALUE, "")):
            return True
        raise FirmwareException(
            "You might have unsupported firmware version %s. Maybe it get updated?"
            % self._firmware_version
        )
