"""Shared entity helpers."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import ZigmaStatusCoordinator


class ZigmaEntity(CoordinatorEntity[ZigmaStatusCoordinator]):
    """Base class for entities belonging to this robot."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: ZigmaStatusCoordinator, host: str, port: int) -> None:
        super().__init__(coordinator)
        self._host = host
        self._port = port
        self._attr_device_info = DeviceInfo(
            identifiers={("zigma_free", f"{host}:{port}")},
            manufacturer="Zigma Free project",
            model="Local control agent",
            name=str(coordinator.data.get("robot") or "Zigma Free robot"),
        )
