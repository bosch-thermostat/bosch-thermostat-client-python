"""`rawscan()` output is posted publicly, so confidential keys must be masked.

`CONFIDENTIAL_URI` blanks a whole `value`. `sgtin` (factory serial) and `dlk`
(HomematicIP link key - the pairing secret) live inside a `value` that is a
list of dicts, so they need per-key masking that keeps the structure a scan is
taken for.
"""

import pytest

from bosch_thermostat_client.helper import (
    CONFIDENTIAL_KEYS,
    deep_into,
    mask_confidential_keys,
)


def test_mask_keeps_structure():
    value = [
        {
            "name": "RWFzeUNvbnRyb2w=",
            "zone": 1,
            "sgtin": "a" * 24,
            "dlk": "b" * 32,
            "battery": "unknown",
        }
    ]
    masked = mask_confidential_keys(value)
    assert masked[0]["sgtin"] == "-1"
    assert masked[0]["dlk"] == "-1"
    assert masked[0]["name"] == "RWFzeUNvbnRyb2w="
    assert masked[0]["zone"] == 1
    assert masked[0]["battery"] == "unknown"


def test_mask_is_recursive():
    masked = mask_confidential_keys(
        {"devices": [{"inner": {"dlk": "secret"}}], "sgtin": "serial"}
    )
    assert masked["sgtin"] == "-1"
    assert masked["devices"][0]["inner"]["dlk"] == "-1"


def test_mask_leaves_scalars_alone():
    assert mask_confidential_keys("21.5") == "21.5"
    assert mask_confidential_keys(7) == 7
    assert mask_confidential_keys(None) is None


def test_confidential_keys_cover_the_reported_fields():
    assert "sgtin" in CONFIDENTIAL_KEYS
    assert "dlk" in CONFIDENTIAL_KEYS


@pytest.mark.asyncio
async def test_deep_into_masks_device_array():
    """The whole path, as rawscan() drives it."""
    tree = {
        "/devices/dev1": {
            "id": "/devices/dev1",
            "type": "deviceArray",
            "value": [
                {
                    "name": "RWFzeUNvbnRyb2w=",
                    "zone": 1,
                    "sgtin": "c" * 24,
                    "dlk": "d" * 32,
                    "type": "thermostat",
                }
            ],
        }
    }

    async def get(url):
        return tree[url]

    result = await deep_into("/devices/dev1", [], get)

    entry = result[0]["value"][0]
    assert entry["sgtin"] == "-1"
    assert entry["dlk"] == "-1"
    assert entry["zone"] == 1
    assert entry["type"] == "thermostat"


@pytest.mark.asyncio
async def test_deep_into_keeps_ordinary_values():
    tree = {
        "/heatingCircuits/hc1/roomtemperature": {
            "id": "/heatingCircuits/hc1/roomtemperature",
            "type": "floatValue",
            "value": 21.5,
        }
    }

    async def get(url):
        return tree[url]

    result = await deep_into("/heatingCircuits/hc1/roomtemperature", [], get)
    assert result[0]["value"] == 21.5


@pytest.mark.asyncio
async def test_deep_into_still_blanks_confidential_uri():
    tree = {"/gateway/uuid": {"id": "/gateway/uuid", "value": "1234567890"}}

    async def get(url):
        return tree[url]

    result = await deep_into("/gateway/uuid", [], get)
    assert result[0]["value"] == "-1"
