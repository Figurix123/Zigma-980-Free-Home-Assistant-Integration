"""Native vacuum entity."""

from __future__ import annotations

from typing import Any

from homeassistant.components.vacuum import (
    StateVacuumEntity,
    VacuumActivity,
    VacuumEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_HOST, CONF_PORT, DOMAIN
from .entity import ZigmaEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the vacuum entity."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [ZigmaVacuum(coordinator, str(entry.data[CONF_HOST]), int(entry.data[CONF_PORT]))]
    )


class ZigmaVacuum(ZigmaEntity, StateVacuumEntity):
    """Control basic cleaning and docking actions."""

    _attr_name = "Vacuum"
    _attr_supported_features = (
        VacuumEntityFeature.STATE
        | VacuumEntityFeature.START
        | VacuumEntityFeature.PAUSE
        | VacuumEntityFeature.RETURN_HOME
    )

    def __init__(self, coordinator, host: str, port: int) -> None:
        super().__init__(coordinator, host, port)
        self._attr_unique_id = f"{host}:{port}_vacuum"

    @property
    def activity(self) -> VacuumActivity | None:
        """Translate native state strings conservatively."""
        status: dict[str, Any] = self.coordinator.data
        working = status.get("working_status")
        error = status.get("error")
        if error not in (None, "", "NoError", "unknown"):
            return VacuumActivity.ERROR
        if working in {"Malfunction", "LocationAlarm"}:
            return VacuumActivity.ERROR
        if working in {"Pause", "paused"}:
            return VacuumActivity.PAUSED
        if working in {"PileCharging", "DirCharging", "charging"}:
            return VacuumActivity.DOCKED
        if working in {"BackCharging", "returning"}:
            return VacuumActivity.RETURNING
        if working in {
            "AutoClean", "SpotClean", "PlanningRect", "PlanningLocation",
            "SelectClean", "DirectionControl", "cleaning",
        }:
            return VacuumActivity.CLEANING
        if working in {"Standby", "Hibernating", "CleanDone", "idle"}:
            return VacuumActivity.IDLE
        return None

    async def async_start(self, **kwargs: Any) -> None:
        """Start a clean or resume a paused clean."""
        action = "resume" if self.activity == VacuumActivity.PAUSED else "clean"
        if action == "clean":
            await self.coordinator.api.async_send_command(
                action, fan_power=self.coordinator.fan_power
            )
        else:
            await self.coordinator.api.async_send_command(action)
        await self.coordinator.async_request_refresh()

    async def async_pause(self) -> None:
        """Pause the current clean."""
        await self.coordinator.api.async_send_command("pause")
        await self.coordinator.async_request_refresh()

    async def async_return_to_base(self, **kwargs: Any) -> None:
        """Return the robot to its dock."""
        await self.coordinator.api.async_send_command("dock")
        await self.coordinator.async_request_refresh()
