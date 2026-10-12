"""Recording sensor Nefit."""
from __future__ import annotations
import asyncio
import logging
from math import ceil
from bosch_thermostat_client.const import RESULT, URI, VALUE, ECUS_RECORDING
from bosch_thermostat_client.const.easycontrol import PAGINATION
from .sensor import Sensor
from bosch_thermostat_client.exceptions import DeviceException

from datetime import timedelta, datetime, timezone

_LOGGER = logging.getLogger(__name__)


class EcusRecordingSensor(Sensor):
    def __init__(self, **kwargs) -> None:
        self._pagination_uri = kwargs.get(PAGINATION)
        self._page_number = None
        self._past_data = {}
        self._entry_data = {}
        self._past_put = set()
        self._lock = asyncio.Lock()
        super().__init__(**kwargs)

    @property
    def kind(self) -> str:
        return ECUS_RECORDING

    def clear_past_data(self, sensor: str):
        self._past_put.add(sensor)
        if self._past_put == set(["ch", "hw"]):
            self._past_data = []

    @property
    def last_entry(self):
        return self._entry_data

    def process_results(self, result, time):
        """Convert multi-level json object to one level object."""

        def get_last_day():
            return time - timedelta(days=1)

        if result and VALUE in result:
            last_reset = get_last_day()
            day = last_reset.strftime("%d-%m-%Y")
            for row in reversed(result[VALUE]):
                if row["d"] == "255-256-65535":
                    continue
                self._entry_data[row["d"]] = row
                if row["d"] == day:
                    self._data[self.attr_id][RESULT][VALUE] = row
                    self._data[self.attr_id][RESULT]["last_reset"] = last_reset.replace(
                        hour=23, minute=59, second=59, microsecond=0
                    )
                    return True

    @property
    def state(self) -> str:
        """Retrieve state of the record sensor."""
        return self._data[self.attr_id].get(RESULT, {}).get(VALUE)

    def build_uri(self, page_number: int = 0) -> str:
        return f"{self._data[self.attr_id][URI]}?page={page_number}"

    async def fetch_all(self):
        async with self._lock:
            if self._past_data:
                return self._past_data
            for i in range(1, self.page_number + 1):
                data = await self._connector.get(self.build_uri(page_number=i))
                if not data:
                    return None
                for row in data.get(VALUE, []):
                    if row["d"] == "255-256-65535":
                        continue
                    self._past_data[row["d"]] = row
            return self._past_data

    @property
    def page_number(self) -> int | None:
        if self._page_number:
            return int(self._page_number)
        return -1

    async def update(self, time: datetime | None = None):
        """Update info about Recording Sensor asynchronously."""
        if time is None:
            time = datetime.now(timezone.utc)
        try:
            pagination = await self._connector.get(self._pagination_uri)
            _page = pagination.get(VALUE, self._page_number)
            if type(_page) == int or type(_page) == float:
                self._page_number = ceil(_page / 32)
        except DeviceException:
            pass
        try:
            if self.page_number > 0:
                self._entry_data = {}
                for i in range(self.page_number, self.page_number + 1):
                    result = await self._connector.get(self.build_uri(page_number=i))
                    self.process_results(result, time)
        except DeviceException as err:
            _LOGGER.error(
                f"Can't update data for {self.name}. Trying uri: {self._data[self.attr_id][URI]}. Error message: {err}"
            )
            self._extra_message = f"Can't update data. Error: {err}"
