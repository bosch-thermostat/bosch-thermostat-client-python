"""Helper functions."""

import re
import logging
from datetime import datetime, timedelta
from bosch_thermostat_client.const import (
    ID,
    NAME,
    PATH,
    RESULT,
    TYPE,
    REGULAR,
    BINARY,
    URI,
    VALUE,
    MAX_VALUE,
    MIN_VALUE,
    UNITS,
    STATUS,
    TIMESTAMP,
    REFERENCES,
    RECORDINGS,
    WRITEABLE,
    INTERVAL,
    USED,
    ENERGY_HISTORY_ENTRIES,
    ENERGY_HISTORY,
)
from bosch_thermostat_client.const.easycontrol import STEP_SIZE
from bosch_thermostat_client.const.ivt import ALLOWED_VALUES, STATE, INVALID

from .exceptions import DeviceException, EncryptionException
import base64

_LOGGER = logging.getLogger(__name__)

HTTP_REGEX = re.compile("http://\\d+\\.\\d+\\.\\d+\\.\\d+/", re.IGNORECASE)

CONFIDENTIAL_URI = (
    "/gateway/uuid",
    "/gateway/user/address",
    "/gateway/user/email",
    "/gateway/user/name",
    "/gateway/user/phone",
    "/system/location/coordinates",
    "/system/location/localization",
    "/gateway/serialnumber",
    "/gateway/remoteServicesPassword",
    "/gateway/identificationKey",
)


def isBase64(s):
    try:
        return base64.b64encode(base64.b64decode(s)) == s
    except Exception:
        return False


def check_base64(s):
    try:
        return base64.b64decode(s).decode("utf-8")
    except Exception:
        return s


def get_all_intervals():
    yesterday = datetime.today() - timedelta(days=1)
    ytt = yesterday.timetuple()
    yttiso = yesterday.isocalendar()
    return [
        f"{ytt[0]}-{ytt[1]}-{ytt[2]}",
        f"{ytt[0]}-{ytt[1]}",
        f"{ytt[0]}-W{yttiso[1]}",
    ]


async def crawl(url, _list, deep, get, exclude):
    """Crawl for Bosch API correct values."""
    try:
        resp = await get(url)
        if (REFERENCES not in resp or deep == 0) and ID in resp:
            if not exclude or not re.match(exclude, resp[ID]):
                _list.append(resp)
        else:
            if REFERENCES in resp:
                for uri in resp[REFERENCES]:
                    if ID in uri and deep > 0:
                        await crawl(uri[ID], _list, deep - 1, get, exclude)
        return _list
    except DeviceException:
        return _list


async def deep_into(url, _list, get):
    """Test for getting references. Used for raw scan."""
    try:
        resp = await get(url)
        new_resp = resp
        if URI in new_resp:
            new_resp[URI] = remove_all_ip_occurs(resp[URI])
        if ENERGY_HISTORY_ENTRIES in new_resp.get(ID, ""):
            page = new_resp.get(VALUE, 1) - 1
            page_uri = f"{ENERGY_HISTORY}?entry={page}"
            en_resp = await get(page_uri)
            en_resp[ID] = page_uri
            _list.append(en_resp)
        if RECORDINGS in new_resp.get(ID, "") and REFERENCES not in new_resp:
            intervals = get_all_intervals()
            for ivs in intervals:
                try:
                    ivs_resp = await get(f"{url}?{INTERVAL}={ivs}")
                    _list.append(ivs_resp)
                except (DeviceException, EncryptionException):
                    pass
        if ID in new_resp and new_resp[ID] in CONFIDENTIAL_URI:
            new_resp[VALUE] = "-1"
            if ALLOWED_VALUES in new_resp:
                new_resp[ALLOWED_VALUES] = ["-1"]
        if "setpointProperty" in new_resp and URI in new_resp["setpointProperty"]:
            new_resp["setpointProperty"][URI] = remove_all_ip_occurs(
                new_resp["setpointProperty"][URI]
            )
        if TYPE in resp and resp[TYPE] == "stringValue":
            new_resp[VALUE] = check_base64(new_resp[VALUE])
        _list.append(resp)
        if REFERENCES in resp:
            for idx, val in enumerate(resp[REFERENCES]):
                val2 = val
                if URI in val2:
                    val2[URI] = remove_all_ip_occurs(val2[URI])
                new_resp[REFERENCES][idx] = val2
                await deep_into(val[ID], _list, get)
    except (DeviceException, EncryptionException):
        pass
    return _list


def remove_all_ip_occurs(data):
    """Change IP to THERMOSTAT string."""
    return HTTP_REGEX.sub("http://THERMOSTAT/", data)


class BoschEntities:
    """Main object to deriver sensors and circuits."""

    def __init__(self, get):
        """
        Initiazlie Bosch entities.

        :param dic requests: { GET: get function, SUBMIT: submit function}
        """
        self._items = []
        self._get = get

    async def retrieve_from_module(self, deep, path, exclude=None):
        """Retrieve all json objects with simple values."""
        return await crawl(path, [], deep, self._get, exclude)

    def get_items(self):
        """Get items."""
        return self._items


class BoschSingleEntity:
    """Object for single sensor/circuit. Don't use it directly."""

    _allowed_types = (REGULAR, BINARY)

    def __init__(self, name, connector, attr_id, path=None, parent=None, **kwargs):
        """Initialize single entity."""
        self._connector = connector
        self._main_data = {NAME: name, ID: attr_id, PATH: path}
        self._data = {}
        self._update_initialized = False
        self._state = False
        self._parent: BoschSingleEntity | None = parent
        self._extra_message = "Waiting to fetch data"

    @property
    def connector(self):
        """Retrieve connector."""
        return self._connector

    @property
    def parent_id(self) -> str | None:
        return self._parent.id if self._parent else None

    def process_results(self, result, key=None, return_data=False):
        """Convert multi-level json object to one level object."""
        data = {} if return_data else self._data[key][RESULT]
        updated = False
        if result:
            for res_key in [
                VALUE,
                MIN_VALUE,
                MAX_VALUE,
                ALLOWED_VALUES,
                UNITS,
                STATUS,
                TIMESTAMP,
                REFERENCES,
                WRITEABLE,
                USED,
                STEP_SIZE,
            ]:
                if res_key in result:
                    value = result[res_key]
                    if res_key in data and data[res_key] == value:
                        continue
                    data[res_key] = value
                    self._update_initialized = True
                    updated = True
        if result and STATE in result:
            for state in result[STATE]:
                for key, item in state.items():
                    if VALUE in data and key == INVALID and data[VALUE] == item:
                        data[INVALID] = True
                    data[STATE + "_" + key] = item
        return data if return_data else updated

    @property
    def state_message(self):
        """Get text state of device"""
        return self._extra_message

    @property
    def update_initialized(self):
        """Inform if we successfully invoked update at least one time."""
        return self._update_initialized

    def get_property(self, property_name):
        """Retrieve JSON with all properties: value, min, max, state etc."""
        return self._data.get(property_name, {}).get(RESULT, {})

    def get_value(self, property_name, default_value=None):
        """Retrieve only value from JSON."""
        ref = self.get_property(property_name)
        return ref.get(VALUE, default_value)

    @property
    def get_all_properties(self):
        return self._data.keys()

    @property
    def get_data(self):
        return self._data

    @property
    def attr_id(self):
        """Get ID of the entity."""
        return self._main_data[ID]

    @property
    def name(self):
        """Name of Bosch entity."""
        return self._main_data[NAME]

    @property
    def id(self):
        """Get ID of Entity."""
        return self.name

    @property
    def path(self):
        """Get path of Bosch API which entity is using for data."""
        return self._main_data[PATH]

    async def update(self):
        """Update info about Circuit asynchronously."""
        state = False
        for key, item in self._data.items():
            if item[TYPE] in self._allowed_types:
                try:
                    result = await self._connector.get(item[URI])
                    self.process_results(result=result, key=key)
                    state = True
                except DeviceException as err:
                    _LOGGER.warning(
                        f"Can't update data for {self.name}. Trying uri: {item[URI]}. Error message: {err}"
                    )
        self._state = state
        if not state:
            self._extra_message = f"Can't update data. Error: {self.name}"


class DeviceClassEntity:
    def __init__(self, device_class, state_class, entity_category):
        """Initialize device class."""
        self._device_class = device_class
        self._state_class = state_class
        self._entity_category = entity_category

    @property
    def device_class(self):
        """Return device class."""
        return self._device_class

    @property
    def state_class(self):
        """Return state class."""
        return self._state_class

    @property
    def entity_category(self):
        """Return Entity category."""
        return self._entity_category
