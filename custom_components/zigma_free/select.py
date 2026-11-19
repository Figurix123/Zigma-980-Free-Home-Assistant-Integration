"""Suction power selection for the next cleaning run."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_FAN_POWER, CONF_HOST, CONF_PORT, DOMAIN, FAN_POWER_OPTIONS
from .coordinator import ZigmaStatusCoordinator
from .entity import ZigmaEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the suction power selector."""
    coordinator: ZigmaStatusCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            ZigmaSuctionPowerSelect(
                coordinator,
                str(entry.data[CONF_HOST]),
                int(entry.data[CONF_PORT]),
                entry,
            )
        ]
    )


class ZigmaSuctionPowerSelect(ZigmaEntity, SelectEntity):
    """Remember the power level to include with the next clean command."""

    _attr_name = "Suction power"
    _attr_icon = "mdi:fan"
    _attr_options = list(FAN_POWER_OPTIONS)

    def __init__(
        self,
        coordinator: ZigmaStatusCoordinator,
        host: str,
        port: int,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator, host, port)
        self._entry = entry
        self._attr_unique_id = f"{host}:{port}_suction_power"
        self._attr_current_option = next(
            (label for label, value in FAN_POWER_OPTIONS.items() if value == coordinator.fan_power),
            "Maximal",
        )

    async def async_select_option(self, option: str) -> None:
        """Save a level for the next full clean; do not command the robot yet."""
        try:
            power = FAN_POWER_OPTIONS[option]
        except KeyError as err:
            raise HomeAssistantError(f"Unsupported suction power option: {option}") from err
        self.coordinator.fan_power = power
        self._attr_current_option = option
        self.hass.config_entries.async_update_entry(
            self._entry,
            options={**self._entry.options, CONF_FAN_POWER: power},
        )
        self.async_write_ha_state()
