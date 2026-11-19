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

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            return await self.api.async_get_status()
        except ZigmaAuthenticationError as err:
            raise ConfigEntryAuthFailed("Robot access key rejected") from err
        except ZigmaApiError as err:
            raise UpdateFailed(str(err)) from err
