"""NEFIT sensors must actually poll their endpoints."""

import asyncio
import json
import logging
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from bosch_thermostat_client.connectors.nefit import NefitConnector
from bosch_thermostat_client.connectors.xmpp import _PendingRequest
from bosch_thermostat_client.const.nefit import NEFIT
from bosch_thermostat_client.sensors import Sensors
from bosch_thermostat_client.sensors.sensor import MISSING_ENDPOINT_WARNING_INTERVAL

DB_DIR = Path(__file__).resolve().parents[1] / "bosch_thermostat_client" / "db"
NEFIT_DBS = sorted((DB_DIR / "nefit").glob("*.json"))


def load_json(path):
    return json.loads(Path(path).read_text())


def nefit_sensors(responses, db_file="022200.json"):
    """Build the NEFIT sensors from the shipped database with a fake connector."""

    async def get(path):
        return responses[path]

    connector = SimpleNamespace(device_type=NEFIT, get=AsyncMock(side_effect=get))
    sensors = Sensors(
        connector=connector,
        sensors_db=load_json(DB_DIR / "nefit" / db_file)["sensors"],
        errors=load_json(DB_DIR / "errorcodes_nefit.json"),
    )
    return connector, {sensor.attr_id: sensor for sensor in sensors}


def ui_status(**fields):
    return {
        "id": "/ecus/rrc/uiStatus",
        "type": "uiUpdate",
        "recordable": 0,
        "writeable": 0,
        "value": {"UMD": "manual", "DHW": "on", **fields},
    }


def cause_code(code):
    return {
        "id": "/system/appliance/causecode",
        "type": "floatValue",
        "recordable": 0,
        "writeable": 0,
        "value": code,
        "unitOfMeasure": "",
        "minValue": 200,
        "maxValue": 65535,
    }


class NefitNotificationTests(unittest.IsolatedAsyncioTestCase):
    async def test_display_code_is_polled(self):
        connector, sensors = nefit_sensors(
            {"/system/appliance/displaycode": {"value": "=H"}}
        )
        await sensors["notifications"].update()
        connector.get.assert_awaited_once_with("/system/appliance/displaycode")
        self.assertEqual(sensors["notifications"].state, "=H")

    async def test_empty_display_code_means_no_notification(self):
        _, sensors = nefit_sensors({"/system/appliance/displaycode": {"value": ""}})
        await sensors["notifications"].update()
        self.assertEqual(sensors["notifications"].state, "No notifications")

    def test_every_nefit_database_marks_notifications(self):
        for db_file in NEFIT_DBS:
            with self.subTest(db=db_file.name):
                _, sensors = nefit_sensors({}, db_file=db_file.name)
                self.assertEqual(sensors["notifications"].kind, "notification")


class NefitBoilerIndicatorTests(unittest.IsolatedAsyncioTestCase):
    async def test_reports_the_bai_field(self):
        for bai in ("CH", "HW", "No"):
            with self.subTest(bai=bai):
                connector, sensors = nefit_sensors(
                    {"/ecus/rrc/uiStatus": ui_status(BAI=bai)}
                )
                await sensors["boiler_indicator"].update()
                connector.get.assert_awaited_once_with("/ecus/rrc/uiStatus")
                self.assertEqual(sensors["boiler_indicator"].state, bai)

    async def test_missing_field_gives_no_value(self):
        _, sensors = nefit_sensors({"/ecus/rrc/uiStatus": ui_status()})
        await sensors["boiler_indicator"].update()
        self.assertIsNone(sensors["boiler_indicator"].state)

    async def test_plain_sensors_keep_their_value(self):
        _, sensors = nefit_sensors({"/system/appliance/actualPower": {"value": 100}})
        await sensors["actualPower"].update()
        self.assertEqual(sensors["actualPower"].state, 100)


class NefitBoilerStatusCodeTests(unittest.IsolatedAsyncioTestCase):
    async def test_reports_the_cause_code(self):
        for code in (203, 283, 201, 204):
            with self.subTest(code=code):
                connector, sensors = nefit_sensors(
                    {"/system/appliance/causecode": cause_code(code)}
                )
                await sensors["boiler_status_code"].update()
                connector.get.assert_awaited_once_with("/system/appliance/causecode")
                self.assertEqual(sensors["boiler_status_code"].state, code)


class NefitDatabaseTests(unittest.TestCase):
    def test_every_nefit_database_has_the_boiler_sensors(self):
        for db_file in NEFIT_DBS:
            with self.subTest(db=db_file.name):
                _, sensors = nefit_sensors({}, db_file=db_file.name)
                self.assertIn("boiler_indicator", sensors)
                self.assertIn("boiler_status_code", sensors)


def xmpp_connector_answering_404():
    """A real NEFIT connector whose gateway answers every GET with a 404."""
    with patch(
        "bosch_thermostat_client.connectors.xmpp.BoschClientXMPP",
        return_value=MagicMock(plugin={}),
    ):
        connector = NefitConnector(
            host="SERIAL", encryption=MagicMock(), access_key="ACCESSKEY"
        )

    async def request(method, path, data=None):
        future = asyncio.get_running_loop().create_future()
        connector._pending = {
            0: _PendingRequest(future=future, method=method, path=path)
        }
        connector.main_listener(
            {"type": "chat", "body": "HTTP/1.0 404 Not Found\r\rSeq-No: 0\r\r"}
        )
        return await future

    connector._request = request
    return connector


class NefitMissingEndpointTests(unittest.IsolatedAsyncioTestCase):
    async def test_xmpp_404_is_throttled(self):
        connector = xmpp_connector_answering_404()
        sensors = Sensors(
            connector=connector,
            sensors_db=load_json(DB_DIR / "nefit" / "021802.json")["sensors"],
            errors=load_json(DB_DIR / "errorcodes_nefit.json"),
        )
        indicator = next(s for s in sensors if s.attr_id == "boiler_indicator")

        with self.assertLogs("bosch_thermostat_client", level=logging.DEBUG) as logs:
            for _ in range(MISSING_ENDPOINT_WARNING_INTERVAL + 1):
                await indicator.update()

        warnings = [r for r in logs.records if r.levelno >= logging.WARNING]
        # One warning on the first poll, one more after the interval, and
        # nothing from the connector itself.
        self.assertEqual(len(warnings), 2)
        self.assertTrue(all(r.name.endswith("sensors.sensor") for r in warnings))
        self.assertIn("HTTP/1.0 404", warnings[0].getMessage())
        self.assertEqual(indicator.state, "unavailable")


if __name__ == "__main__":
    unittest.main()
