"""NEFIT sensors must actually poll their endpoints."""

import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from bosch_thermostat_client.const.nefit import NEFIT
from bosch_thermostat_client.sensors import Sensors

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


if __name__ == "__main__":
    unittest.main()
