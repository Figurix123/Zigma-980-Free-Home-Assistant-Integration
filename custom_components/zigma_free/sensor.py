"""Status and diagnostic sensors."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_HOST, CONF_PORT, DOMAIN
from .coordinator import ZigmaStatusCoordinator
from .entity import ZigmaEntity


@dataclass(frozen=True, kw_only=True)
class ZigmaSensorDescription(SensorEntityDescription):
    """Describe a status field."""


SENSORS = (
    ZigmaSensorDescription(
        key="battery_level",
        name="Battery",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    ZigmaSensorDescription(
        key="clean_time_s",
        name="Cleaning time",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    ZigmaSensorDescription(
        key="clean_area_m2",
        name="Cleaning area (API value)",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    ZigmaSensorDescription(
        key="working_status",
        name="Native status",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    ZigmaSensorDescription(
        key="error",
        name="Native error",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    ZigmaSensorDescription(
        key="telemetry_state",
        name="Telemetry freshness",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensors."""
    coordinator: ZigmaStatusCoordinator = hass.data[DOMAIN][entry.entry_id]
    host, port = str(entry.data[CONF_HOST]), int(entry.data[CONF_PORT])
    async_add_entities(
        ZigmaStatusSensor(coordinator, host, port, description)
        for description in SENSORS
    )


class ZigmaStatusSensor(ZigmaEntity, SensorEntity):
    """Expose one status field without inventing a fallback value."""

    entity_description: ZigmaSensorDescription

    def __init__(
        self,
        coordinator: ZigmaStatusCoordinator,
        host: str,
        port: int,
        description: ZigmaSensorDescription,
    ) -> None:
        super().__init__(coordinator, host, port)
        self.entity_description = description
        self._attr_unique_id = f"{host}:{port}_{description.key}"
        self._attr_entity_category = description.entity_category

    @property
    def native_value(self) -> Any:
        """Return the API value when present."""
        return self.coordinator.data.get(self.entity_description.key)
