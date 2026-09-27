"""A raw scan must not leak personal data: users are asked to share it."""

import unittest

from bosch_thermostat_client.helper import deep_into

PERSONAL = {
    "/ecus/rrc/personaldetails": "Test User;0000000000;user@example.com",
    "/ecus/rrc/installerdetails": "Example Heating;0000000000",
    "/ecus/rrc/registrationdetails": "Test User;1 Example Street",
    "/ecus/rrc/homeentrancedetection/userprofile0/name": "Test User",
    "/ecus/rrc/homeentrancedetection/userprofile9/name": "Guest",
    "/system/appliance/serialnumber": "0000000000-0000000000-000000",
    "/system/location/latitude": 12.3456789,
    "/system/location/longitude": 1.2345678,
}
PUBLIC = {
    "/ecus/rrc/temperaturestep": 0.5,
    "/ecus/rrc/homeentrancedetection/userprofile0/temperature": 18.0,
    "/system/appliance/causecode": 203,
}


def leaf(path, value):
    kind = "stringValue" if isinstance(value, str) else "floatValue"
    return {"id": path, "type": kind, "writeable": 1, "value": value}


async def scan():
    tree = {"/root": {"id": "/root", "references": []}}
    for path, value in {**PERSONAL, **PUBLIC}.items():
        tree[path] = leaf(path, value)
        tree["/root"]["references"].append({"id": path})

    async def get(path):
        return tree[path]

    return {item["id"]: item for item in await deep_into("/root", [], get)}


class RawscanPrivacyTests(unittest.IsolatedAsyncioTestCase):
    async def test_personal_data_is_masked(self):
        result = await scan()
        for path in PERSONAL:
            with self.subTest(path=path):
                self.assertEqual(result[path]["value"], "-1")

    async def test_other_values_are_kept(self):
        result = await scan()
        for path, value in PUBLIC.items():
            with self.subTest(path=path):
                self.assertEqual(result[path]["value"], value)


if __name__ == "__main__":
    unittest.main()
