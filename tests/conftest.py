"""Shared test fixtures for Behaviour Monitor tests."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def mock_hass() -> MagicMock:
    """Create a mock Home Assistant instance."""
    hass = MagicMock()
    hass.data = {}
    hass.states = MagicMock()
    hass.states.async_all = MagicMock(return_value=[])
    hass.bus = MagicMock()
    hass.bus.async_listen = MagicMock(return_value=MagicMock())
    hass.services = MagicMock()
    hass.services.async_call = AsyncMock()
    hass.async_create_task = MagicMock()
    hass.config_entries = MagicMock()
    hass.config_entries.async_forward_entry_setups = AsyncMock()
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
    hass.config_entries.async_reload = AsyncMock()
    return hass


@pytest.fixture
def mock_config_entry() -> MagicMock:
    """Create a mock config entry."""
    entry = MagicMock()
    entry.entry_id = "test_entry_id"
    entry.data = {
        "monitored_entities": ["sensor.test1", "sensor.test2"],
        "sensitivity": "medium",
        "learning_period": 7,
        "enable_notifications": True,
        "enable_ml": True,
        "retrain_period": 14,
        "cross_sensor_window": 300,
    }
    entry.add_update_listener = MagicMock(return_value=MagicMock())
    entry.async_on_unload = MagicMock()
    return entry


@pytest.fixture
def sample_timestamps() -> list[datetime]:
    """Generate sample timestamps for testing."""
    base = datetime(2024, 1, 15, 9, 0, 0)  # Monday 9:00 AM
    return [base + timedelta(minutes=i * 15) for i in range(10)]


@pytest.fixture
def weekday_timestamps() -> dict[int, list[datetime]]:
    """Generate timestamps for each day of the week."""
    timestamps: dict[int, list[datetime]] = {}
    base = datetime(2024, 1, 15, 9, 0, 0)  # Monday

    for day_offset in range(7):
        day_base = base + timedelta(days=day_offset)
        timestamps[day_base.weekday()] = [
            day_base + timedelta(hours=h) for h in range(24)
        ]

    return timestamps
