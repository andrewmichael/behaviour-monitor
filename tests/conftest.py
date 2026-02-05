"""Shared test fixtures for Behaviour Monitor tests."""

from __future__ import annotations

import sys
from datetime import datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# Mock Home Assistant modules before any imports from custom_components
# This allows tests to run without installing the full Home Assistant package
def _setup_ha_mocks():
    """Set up mock Home Assistant modules."""

    # Create base mock modules
    mock_ha = MagicMock()
    mock_ha_core = MagicMock()
    mock_ha_helpers = MagicMock()
    mock_ha_components = MagicMock()
    mock_ha_const = MagicMock()
    mock_ha_util = MagicMock()

    # Mock homeassistant.core
    mock_ha_core.HomeAssistant = MagicMock
    mock_ha_core.Event = MagicMock
    mock_ha_core.ServiceCall = MagicMock
    mock_ha_core.callback = lambda func: func

    # Mock homeassistant.const
    class MockPlatform:
        """Mock Platform enum."""
        SENSOR = "sensor"
        SWITCH = "switch"
        SELECT = "select"
        BINARY_SENSOR = "binary_sensor"

    mock_ha_const.Platform = MockPlatform
    mock_ha_const.EVENT_STATE_CHANGED = "state_changed"
    mock_ha_const.CONF_NAME = "name"

    # Mock homeassistant.config_entries
    class MockConfigFlow:
        """Mock ConfigFlow base class."""

        def __init_subclass__(cls, domain=None, **kwargs):
            """Support domain keyword in class definition."""
            super().__init_subclass__(**kwargs)
            if domain is not None:
                cls.domain = domain

        def async_show_form(self, step_id, data_schema=None, errors=None, description_placeholders=None, suggested_values=None):
            """Mock show form method (not actually async despite the name)."""
            return {
                "type": "form",
                "step_id": step_id,
                "data_schema": data_schema,
                "errors": errors or {},
                "description_placeholders": description_placeholders,
                "suggested_values": suggested_values,
            }

        def async_create_entry(self, title, data, description=None, description_placeholders=None):
            """Mock create entry method."""
            return {
                "type": "create_entry",
                "title": title,
                "data": data,
                "description": description,
                "description_placeholders": description_placeholders,
            }

        async def async_set_unique_id(self, unique_id):
            """Mock set unique id method."""
            self._unique_id = unique_id

        def _abort_if_unique_id_configured(self):
            """Mock abort if unique id configured."""
            pass

    class MockOptionsFlow:
        """Mock OptionsFlow base class."""
        def __init__(self):
            pass

        def async_show_form(self, step_id, data_schema=None, errors=None, description_placeholders=None, suggested_values=None):
            """Mock show form method."""
            return {
                "type": "form",
                "step_id": step_id,
                "data_schema": data_schema,
                "errors": errors or {},
                "description_placeholders": description_placeholders,
                "suggested_values": suggested_values,
            }

        def async_create_entry(self, title="", data=None):
            """Mock create entry method."""
            return {
                "type": "create_entry",
                "title": title,
                "data": data or {},
            }

    mock_config_entries = MagicMock()
    mock_config_entries.ConfigEntry = MagicMock
    mock_config_entries.ConfigFlow = MockConfigFlow
    mock_config_entries.ConfigFlowResult = dict
    mock_config_entries.OptionsFlow = MockOptionsFlow

    # Mock homeassistant.helpers modules
    mock_ha_helpers.config_validation = MagicMock()
    mock_ha_helpers.entity_registry = MagicMock()
    mock_ha_helpers.entity = MagicMock()
    mock_ha_helpers.entity_platform = MagicMock()
    mock_ha_helpers.selector = MagicMock()

    # Mock Storage with proper async methods
    class MockStore:
        """Mock Home Assistant storage."""
        def __init__(self, hass, version, key):
            self.hass = hass
            self.version = version
            self.key = key
            self._data = None

        async def async_load(self):
            """Mock async load."""
            return self._data

        async def async_save(self, data):
            """Mock async save."""
            self._data = data

    mock_ha_helpers.storage = MagicMock()
    mock_ha_helpers.storage.Store = MockStore

    # Mock CoordinatorEntity and DataUpdateCoordinator
    class MockCoordinatorEntity:
        """Mock CoordinatorEntity base class."""
        def __init__(self, coordinator):
            self.coordinator = coordinator
            self._attr_unique_id = None
            self._attr_name = None
            self._attr_device_info = None
            self._attr_entity_registry_enabled_default = True

        @property
        def unique_id(self):
            """Return unique ID."""
            return self._attr_unique_id

        @property
        def name(self):
            """Return name."""
            return self._attr_name

        @property
        def device_info(self):
            """Return device info."""
            return self._attr_device_info

        @classmethod
        def __class_getitem__(cls, item):
            """Support generic type subscripting like CoordinatorEntity[Coordinator]."""
            return cls

    class MockDataUpdateCoordinator:
        """Mock DataUpdateCoordinator."""
        def __init__(self, hass, logger, name, update_interval):
            self.hass = hass
            self.logger = logger
            self.name = name
            self.update_interval = update_interval
            self.data = None
            self._listeners = []

        async def async_config_entry_first_refresh(self):
            """Mock refresh."""
            pass

        async def async_request_refresh(self):
            """Mock request refresh."""
            pass

        async def async_refresh(self):
            """Mock refresh."""
            pass

        def async_add_listener(self, listener):
            """Mock add listener."""
            self._listeners.append(listener)
            return lambda: self._listeners.remove(listener)

        @classmethod
        def __class_getitem__(cls, item):
            """Support generic type subscripting like DataUpdateCoordinator[dict]."""
            return cls

    mock_update_coordinator = MagicMock()
    mock_update_coordinator.CoordinatorEntity = MockCoordinatorEntity
    mock_update_coordinator.DataUpdateCoordinator = MockDataUpdateCoordinator
    mock_ha_helpers.update_coordinator = mock_update_coordinator

    # Mock entity base classes
    mock_ha_helpers.entity.DeviceInfo = dict
    mock_ha_helpers.entity_platform.AddEntitiesCallback = MagicMock()

    # Mock sensor component
    mock_sensor = MagicMock()

    class MockSensorEntity:
        """Mock SensorEntity base class."""
        def __init__(self):
            self._attr_unique_id = None
            self._attr_name = None
            self._attr_device_info = None
            self._attr_native_value = None
            self._attr_extra_state_attributes = {}

        @property
        def unique_id(self):
            """Return unique ID."""
            return self._attr_unique_id

        @property
        def name(self):
            """Return name."""
            return self._attr_name

        @property
        def native_value(self):
            """Return native value."""
            return self._attr_native_value

        @property
        def extra_state_attributes(self):
            """Return extra state attributes."""
            return self._attr_extra_state_attributes

    # Import dataclass decorator for proper mock
    from dataclasses import dataclass as real_dataclass

    @real_dataclass(frozen=True)
    class MockSensorEntityDescription:
        """Mock SensorEntityDescription as a frozen dataclass."""
        key: str
        name: str = None
        icon: str = None
        device_class: Any = None
        state_class: Any = None
        native_unit_of_measurement: str = None
        entity_category: Any = None
        entity_registry_enabled_default: bool = True

    mock_sensor.SensorEntity = MockSensorEntity
    mock_sensor.SensorEntityDescription = MockSensorEntityDescription
    mock_sensor.SensorDeviceClass = MagicMock()
    mock_sensor.SensorStateClass = MagicMock()

    # Mock select component
    mock_select = MagicMock()

    class MockSelectEntity:
        """Mock SelectEntity base class."""
        def __init__(self):
            self._attr_unique_id = None
            self._attr_name = None
            self._attr_device_info = None
            self._attr_current_option = None
            self._attr_options = []

        @property
        def unique_id(self):
            """Return unique ID."""
            return self._attr_unique_id

        @property
        def current_option(self):
            """Return current option."""
            return self._attr_current_option

        async def async_select_option(self, option):
            """Select an option."""
            self._attr_current_option = option

    mock_select.SelectEntity = MockSelectEntity

    # Mock switch component
    mock_switch = MagicMock()

    class MockSwitchEntity:
        """Mock SwitchEntity base class."""
        def __init__(self):
            self._attr_unique_id = None
            self._attr_name = None
            self._attr_device_info = None
            self._attr_is_on = False

        @property
        def unique_id(self):
            """Return unique ID."""
            return self._attr_unique_id

        @property
        def is_on(self):
            """Return if switch is on."""
            return self._attr_is_on

        async def async_turn_on(self, **kwargs):
            """Turn the switch on."""
            self._attr_is_on = True

        async def async_turn_off(self, **kwargs):
            """Turn the switch off."""
            self._attr_is_on = False

    mock_switch.SwitchEntity = MockSwitchEntity

    # Mock components
    mock_components = MagicMock()
    mock_components.sensor = mock_sensor
    mock_components.select = mock_select
    mock_components.switch = mock_switch

    # Mock dt utilities
    mock_dt_util = MagicMock()
    mock_dt_util.now = datetime.now
    mock_dt_util.parse_datetime = lambda x: datetime.fromisoformat(x) if x else None
    mock_ha_util.dt = mock_dt_util

    # Mock voluptuous (used by HA for schema validation)
    mock_voluptuous = MagicMock()
    mock_voluptuous.Required = lambda x, **kwargs: x
    mock_voluptuous.Optional = lambda x, **kwargs: x
    mock_voluptuous.Schema = lambda x: x
    mock_voluptuous.All = lambda *args: args[0] if args else None
    mock_voluptuous.Range = lambda *args, **kwargs: lambda x: x
    mock_voluptuous.In = lambda x: lambda v: v

    # Install all mocks in sys.modules
    sys.modules['homeassistant'] = mock_ha
    sys.modules['homeassistant.core'] = mock_ha_core
    sys.modules['homeassistant.const'] = mock_ha_const
    sys.modules['homeassistant.config_entries'] = mock_config_entries
    sys.modules['homeassistant.helpers'] = mock_ha_helpers
    sys.modules['homeassistant.helpers.config_validation'] = mock_ha_helpers.config_validation
    sys.modules['homeassistant.helpers.entity_registry'] = mock_ha_helpers.entity_registry
    sys.modules['homeassistant.helpers.entity'] = mock_ha_helpers.entity
    sys.modules['homeassistant.helpers.entity_platform'] = mock_ha_helpers.entity_platform
    sys.modules['homeassistant.helpers.selector'] = mock_ha_helpers.selector
    sys.modules['homeassistant.helpers.storage'] = mock_ha_helpers.storage
    sys.modules['homeassistant.helpers.update_coordinator'] = mock_update_coordinator
    sys.modules['homeassistant.components'] = mock_components
    sys.modules['homeassistant.components.sensor'] = mock_sensor
    sys.modules['homeassistant.components.select'] = mock_select
    sys.modules['homeassistant.components.switch'] = mock_switch
    sys.modules['homeassistant.util'] = mock_ha_util
    sys.modules['homeassistant.util.dt'] = mock_dt_util
    sys.modules['voluptuous'] = mock_voluptuous


# Set up mocks before pytest collects tests
_setup_ha_mocks()


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
    # Use a simple object instead of MagicMock to avoid spec issues
    class MockConfigEntry:
        """Mock config entry object."""
        def __init__(self):
            self.entry_id = "test_entry_id"
            self.data = {
                "monitored_entities": ["sensor.test1", "sensor.test2"],
                "sensitivity": "medium",
                "learning_period": 7,
                "enable_notifications": True,
                "enable_ml": True,
                "retrain_period": 14,
                "cross_sensor_window": 300,
            }
            self.options = {}
            self.add_update_listener = MagicMock(return_value=MagicMock())
            self.async_on_unload = MagicMock()

    return MockConfigEntry()


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
