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
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_HOST, CONF_PORT, DOMAIN
from .coordinator import ZigmaSchedulesCoordinator, ZigmaStatusCoordinator
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
        [ZigmaStatusSensor(coordinator, host, port, description) for description in SENSORS]
        + ([ZigmaSchedulesSensor(
            coordinator.schedule_coordinator,
            host,
            port,
            str(coordinator.data.get("robot") or "Zigma Free robot"),
        )]
           if coordinator.schedule_coordinator is not None else [])
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


class ZigmaSchedulesSensor(CoordinatorEntity[ZigmaSchedulesCoordinator], SensorEntity):
    """Expose schedule summaries without leaking custom shell commands."""

    _attr_has_entity_name = True
    _attr_name = "Schedules"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self, coordinator: ZigmaSchedulesCoordinator, host: str, port: int, robot_name: str
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{host}:{port}_schedules"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{host}:{port}")},
            manufacturer="Zigma Free project",
            model="Local control agent",
            name=robot_name,
        )

    @property
    def native_value(self) -> int | None:
        """Return the number of configured schedules."""
        if not self.coordinator.data:
            return None
        return len(self.coordinator.data.get("items", []))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return safe schedule fields and cron installation status."""
        data = self.coordinator.data or {}
        allowed = (
            "id", "label", "time", "days", "enabled", "action", "fan_power",
            "next_run", "last_result", "execution_method",
        )
        schedules = [
            {key: item[key] for key in allowed if key in item}
            for item in data.get("items", [])
            if isinstance(item, dict)
        ]
        cron = data.get("cron") or {}
        return {
            "installed": data.get("installed"),
            "cron_available": cron.get("available"),
            "cron_running": cron.get("running"),
            "robot_time_basis": "Robot local time; timezone not confirmed by API",
            "schedules": schedules,
        }
