"""Config flow for Zigma Free."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import ZigmaAuthenticationError, ZigmaLocalApi, ZigmaApiError
from .const import CONF_ACCESS_KEY, CONF_HOST, CONF_PORT, DEFAULT_PORT, DOMAIN


class ZigmaFreeConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a user configured robot."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Ask for the robot address and test the credentials."""
        errors: dict[str, str] = {}
        if user_input is not None:
            host = str(user_input[CONF_HOST]).strip()
            port = int(user_input[CONF_PORT])
            await self.async_set_unique_id(f"{host}:{port}")
            self._abort_if_unique_id_configured()
            api = ZigmaLocalApi(
                async_get_clientsession(self.hass),
                host,
                port,
                str(user_input[CONF_ACCESS_KEY]),
            )
            try:
                status = await api.async_get_status()
            except ZigmaAuthenticationError:
                errors["base"] = "invalid_auth"
            except ZigmaApiError:
                errors["base"] = "cannot_connect"
            else:
                title = str(status.get("robot") or f"Zigma Free ({host})")
                return self.async_create_entry(
                    title=title,
                    data={
                        CONF_HOST: host,
                        CONF_PORT: port,
                        CONF_ACCESS_KEY: str(user_input[CONF_ACCESS_KEY]),
                    },
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_HOST): cv.string,
                vol.Optional(CONF_PORT, default=DEFAULT_PORT): vol.All(
                    vol.Coerce(int), vol.Range(min=1, max=65535)
                ),
                vol.Required(CONF_ACCESS_KEY): cv.string,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> config_entries.ConfigFlowResult:
        """Start the access-key renewal flow."""
        self._reauth_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Validate and save a replacement access key."""
        entry = self._reauth_entry
        if entry is None:
            return self.async_abort(reason="unknown")
        errors: dict[str, str] = {}
        if user_input is not None:
            host = str(entry.data[CONF_HOST])
            port = int(entry.data[CONF_PORT])
            access_key = str(user_input[CONF_ACCESS_KEY])
            api = ZigmaLocalApi(
                async_get_clientsession(self.hass), host, port, access_key
            )
            try:
                await api.async_get_status()
            except ZigmaAuthenticationError:
                errors["base"] = "invalid_auth"
            except ZigmaApiError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_ACCESS_KEY: access_key}
                )
        schema = vol.Schema({vol.Required(CONF_ACCESS_KEY): cv.string})
        return self.async_show_form(
            step_id="reauth_confirm", data_schema=schema, errors=errors
        )
