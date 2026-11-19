"""Status polling coordinator."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .api import ZigmaApiError, ZigmaAuthenticationError, ZigmaLocalApi
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN


class ZigmaStatusCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Poll only the lightweight status document."""

    def __init__(self, hass: HomeAssistant, api: ZigmaLocalApi) -> None:
        super().__init__(
            hass,
            logger=logging.getLogger(__name__),
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )
        self.api = api
        self.schedule_coordinator: ZigmaSchedulesCoordinator | None = None

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            return await self.api.async_get_status()
        except ZigmaAuthenticationError as err:
            raise ConfigEntryAuthFailed("Robot access key rejected") from err
        except ZigmaApiError as err:
            raise UpdateFailed(str(err)) from err

def _schedule_payload(item: dict[str, Any]) -> dict[str, Any]:
    """Match the supported PUT payload used by the release web interface."""
    action = str(item.get("action") or "clean")
    payload: dict[str, Any] = {
        key: item.get(key)
        for key in (
            "id", "label", "time", "days", "enabled", "confirm_action",
            "master_uid", "master_revision", "master_name",
        )
        if key in item
    }
    payload["action"] = action
    payload["confirm_action"] = bool(item.get("confirm_action"))
    if action == "clean" and item.get("fan_power") is not None:
        payload["fan_power"] = item["fan_power"]
    if action == "play_song" and item.get("song") is not None:
        payload["song"] = item["song"]
    if action == "custom_command" and item.get("command") is not None:
        payload["command"] = item["command"]
    return payload


class ZigmaSchedulesCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Refresh schedules slowly; unlike status they are not live telemetry."""

    def __init__(self, hass: HomeAssistant, api: ZigmaLocalApi) -> None:
        super().__init__(
            hass,
            logger=logging.getLogger(__name__),
            name=f"{DOMAIN} schedules",
            update_interval=timedelta(minutes=5),
        )
        self.api = api

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            result = await self.api.async_get_schedules()
            if not isinstance(result.get("items"), list):
                raise ZigmaApiError("Schedule response did not contain an items list")
            return result
        except ZigmaAuthenticationError as err:
            raise ConfigEntryAuthFailed("Robot access key rejected") from err
        except ZigmaApiError as err:
            raise UpdateFailed(str(err)) from err

    async def async_set_schedule_enabled(self, schedule_id: str, enabled: bool) -> None:
        """Change one schedule flag while preserving the other jobs."""
        current = await self.api.async_get_schedules()
        items = current.get("items")
        if not isinstance(items, list):
            raise ZigmaApiError("Schedule response did not contain an items list")
        found = False
        updated: list[dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            if str(item.get("id")) == schedule_id:
                item = {**item, "enabled": enabled}
                found = True
            updated.append(_schedule_payload(item))
        if not found:
            raise ZigmaApiError(f"Schedule {schedule_id} no longer exists")
        await self.api.async_put_schedules(updated)
        await self.async_request_refresh()
