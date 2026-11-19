"""Safe enable/disable controls for ordinary robot schedules."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_HOST, CONF_PORT, DOMAIN
from .coordinator import ZigmaSchedulesCoordinator, ZigmaStatusCoordinator

_SAFE_SCHEDULE_ACTIONS = {"clean", "dock", "play_song", "random_song"}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create switches for supported existing schedules."""
    status: ZigmaStatusCoordinator = hass.data[DOMAIN][entry.entry_id]
    schedules = status.schedule_coordinator
    if schedules is None or not schedules.data:
        return
    host, port = str(entry.data[CONF_HOST]), int(entry.data[CONF_PORT])
    robot_name = str(status.data.get("robot") or "Zigma Free robot")
    added_ids: set[str] = set()

    @callback
    def add_schedule_entities() -> None:
        """Add controls when schedules are created on the robot later."""
        jobs = (schedules.data or {}).get("items", [])
        entities = []
        for job in jobs:
            if (
                not isinstance(job, dict)
                or str(job.get("action") or "clean") not in _SAFE_SCHEDULE_ACTIONS
                or job.get("id") is None
            ):
                continue
            schedule_id = str(job["id"])
            if schedule_id in added_ids:
                continue
            added_ids.add(schedule_id)
            entities.append(ZigmaScheduleSwitch(schedules, host, port, robot_name, job))
        if entities:
            async_add_entities(entities)

    entry.async_on_unload(schedules.async_add_listener(add_schedule_entities))
    add_schedule_entities()


class ZigmaScheduleSwitch(CoordinatorEntity[ZigmaSchedulesCoordinator], SwitchEntity):
    """Enable or disable one existing schedule without running it immediately."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ZigmaSchedulesCoordinator,
        host: str,
        port: int,
        robot_name: str,
        job: dict[str, Any],
    ) -> None:
        super().__init__(coordinator)
        self._schedule_id = str(job["id"])
        self._attr_name = str(job.get("label") or f"Schedule {self._schedule_id}")
        self._attr_unique_id = f"{host}:{port}_schedule_{self._schedule_id}"
        self._attr_icon = "mdi:calendar-clock"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{host}:{port}")},
            manufacturer="Zigma Free project",
            model="Local control agent",
            name=robot_name,
        )

    @property
    def _job(self) -> dict[str, Any] | None:
        """Return the latest copy of this job."""
        for item in (self.coordinator.data or {}).get("items", []):
            if isinstance(item, dict) and str(item.get("id")) == self._schedule_id:
                return item
        return None

    @property
    def available(self) -> bool:
        """Mark schedules removed outside HA as unavailable."""
        return self.coordinator.last_update_success and self._job is not None

    @property
    def is_on(self) -> bool:
        """Return the robot's current enabled flag."""
        return bool((self._job or {}).get("enabled"))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose the schedule details without shell command contents."""
        job = self._job or {}
        return {
            key: job[key]
            for key in ("time", "days", "action", "fan_power", "next_run", "last_result")
            if key in job
        }

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable this scheduled action; it will run at its next scheduled time."""
        await self.coordinator.async_set_schedule_enabled(self._schedule_id, True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable this schedule without deleting it."""
        await self.coordinator.async_set_schedule_enabled(self._schedule_id, False)
