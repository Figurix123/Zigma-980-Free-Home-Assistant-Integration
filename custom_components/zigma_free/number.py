"""Robot settings exposed as Home Assistant number entities."""

from __future__ import annotations

import math
from typing import Any

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import ZigmaApiError
from .const import CONF_HOST, CONF_PORT, DOMAIN
from .coordinator import ZigmaSettingsCoordinator, ZigmaStatusCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the speaker-volume setting."""
    status: ZigmaStatusCoordinator = hass.data[DOMAIN][entry.entry_id]
    settings = status.settings_coordinator
    if settings is None:
        return
    host, port = str(entry.data[CONF_HOST]), int(entry.data[CONF_PORT])
    async_add_entities([ZigmaSpeakerVolume(settings, host, port, status.data)])


class ZigmaSpeakerVolume(CoordinatorEntity[ZigmaSettingsCoordinator], NumberEntity):
    """Read or change the speaker volume from 0 to 100 percent."""

    _attr_has_entity_name = True
    _attr_name = "Speaker volume"
    _attr_icon = "mdi:volume-high"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_mode = NumberMode.SLIDER

    def __init__(
        self,
        coordinator: ZigmaSettingsCoordinator,
        host: str,
        port: int,
        status: dict[str, Any],
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{host}:{port}_speaker_volume"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{host}:{port}")},
            manufacturer="Zigma Free project",
            model="Local control agent",
            name=str(status.get("robot") or "Zigma Free robot"),
        )

    @property
    def native_value(self) -> float | None:
        """Return the current volume if the robot reports a valid value."""
        volume = (self.coordinator.data or {}).get("volume")
        if (
            isinstance(volume, (int, float))
            and not isinstance(volume, bool)
            and math.isfinite(volume)
            and 0 <= volume <= 100
        ):
            return float(volume)
        return None

    @property
    def available(self) -> bool:
        """Require a fresh settings response with a valid volume value."""
        return super().available and self.native_value is not None

    async def async_set_native_value(self, value: float) -> None:
        """Set the speaker volume and update the displayed setting optimistically."""
        if (
            isinstance(value, bool)
            or not math.isfinite(value)
            or not 0 <= value <= 100
            or not float(value).is_integer()
        ):
            raise HomeAssistantError("Speaker volume must be a whole number from 0 to 100")
        volume = int(value)
        try:
            await self.coordinator.api.async_set_setting("volume", volume)
        except ZigmaApiError as err:
            raise HomeAssistantError(f"Could not set robot speaker volume: {err}") from err
        self.coordinator.async_set_updated_data(
            {**(self.coordinator.data or {}), "volume": volume}
        )
