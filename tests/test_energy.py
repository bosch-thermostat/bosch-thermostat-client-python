"""Tests for page_number validation in fetch_range.

EnergySensor.fetch_range() should return an empty dictionary immediately 
if page_number is invalid (<= 0) to prevent unnecessary iteration and I/O.
"""
import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from bosch_thermostat_client.sensors.energy import EnergySensor


def _make_sensor(connector=None):
    """Construct a minimal EnergySensor."""
    if connector is None:
        connector = AsyncMock()
    sensor = EnergySensor(
        attr_id="energySensor",
        path="/energy/test",
        connector=connector,
        name="energy_test",
        pagination="/energy/pagination",
    )
    return sensor


@pytest.mark.asyncio
async def test_fetch_range_no_pages():
    """Verify fetch_range returns {} and skips I/O when page_number is 0."""
    connector = AsyncMock()
    sensor = _make_sensor(connector=connector)
    
    # Mock page_number to return 0
    with patch.object(
        type(sensor), "page_number", new_callable=lambda: property(lambda s: 0)
    ):
        yesterday = datetime.today() - timedelta(days=1)
        result = await sensor.fetch_range(yesterday, yesterday)

    assert result == {}
    # Ensure no network calls were made
    connector.get.assert_not_called()


@pytest.mark.asyncio
async def test_fetch_range_negative_pages():
    """Verify fetch_range returns {} and skips I/O when page_number is negative."""
    connector = AsyncMock()
    sensor = _make_sensor(connector=connector)
    
    # Mock page_number to return -1 (typical for uninitialized or error state)
    with patch.object(
        type(sensor), "page_number", new_callable=lambda: property(lambda s: -1)
    ):
        yesterday = datetime.today() - timedelta(days=1)
        result = await sensor.fetch_range(yesterday, yesterday)

    assert result == {}
    # Ensure no network calls were made
    connector.get.assert_not_called()
