"""Direct command buttons for the robot."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_HOST, CONF_PORT, DOMAIN
from .coordinator import ZigmaStatusCoordinator
from .entity import ZigmaEntity


BUTTONS = (
    ButtonEntityDescription(key="clean", name="Clean", icon="mdi:play"),
    ButtonEntityDescription(key="resume", name="Resume", icon="mdi:play-circle"),
    ButtonEntityDescription(key="pause", name="Pause", icon="mdi:pause"),
    ButtonEntityDescription(key="dock", name="Dock", icon="mdi:home-map-marker"),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up direct command buttons."""
    coordinator: ZigmaStatusCoordinator = hass.data[DOMAIN][entry.entry_id]
    host, port = str(entry.data[CONF_HOST]), int(entry.data[CONF_PORT])
    async_add_entities(
        ZigmaCommandButton(coordinator, host, port, description)
        for description in BUTTONS
    )


class ZigmaCommandButton(ZigmaEntity, ButtonEntity):
    """Dispatch one explicit command when pressed."""

    entity_description: ButtonEntityDescription

    def __init__(
        self,
        coordinator: ZigmaStatusCoordinator,
        host: str,
        port: int,
        description: ButtonEntityDescription,
    ) -> None:
        super().__init__(coordinator, host, port)
        self.entity_description = description
        self._attr_unique_id = f"{host}:{port}_{description.key}"

    async def async_press(self) -> None:
        """Send the command associated with this button."""
        action = self.entity_description.key
        if action == "clean":
            await self.coordinator.api.async_send_command(
                action, fan_power=self.coordinator.fan_power
            )
        else:
            await self.coordinator.api.async_send_command(action)
        await self.coordinator.async_request_refresh()
