"""Zigma Free integration setup."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import ZigmaLocalApi
from .const import CONF_ACCESS_KEY, CONF_HOST, CONF_PORT, DOMAIN, PLATFORMS
from .coordinator import ZigmaSchedulesCoordinator, ZigmaStatusCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the configured robot."""
    api = ZigmaLocalApi(
        async_get_clientsession(hass),
        str(entry.data[CONF_HOST]),
        int(entry.data[CONF_PORT]),
        str(entry.data[CONF_ACCESS_KEY]),
    )
    coordinator = ZigmaStatusCoordinator(hass, api)
    try:
        await coordinator.async_config_entry_first_refresh()
    except ConfigEntryAuthFailed:
        raise
    except Exception as err:
        raise ConfigEntryNotReady(f"Could not read robot status: {err}") from err

    schedules = ZigmaSchedulesCoordinator(hass, api)
    try:
        await schedules.async_config_entry_first_refresh()
    except ConfigEntryAuthFailed:
        raise
    except Exception as err:
        # A schedule endpoint failure must not take the working vacuum offline.
        _LOGGER.warning("Could not read robot schedules: %s", err)
    coordinator.schedule_coordinator = schedules

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload the configured robot."""
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False
    hass.data[DOMAIN].pop(entry.entry_id)
    return True
