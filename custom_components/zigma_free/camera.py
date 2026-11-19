"""On-demand camera snapshot for the robot's current map."""

from __future__ import annotations

import struct
import time
import zlib
from typing import Any

from homeassistant.components.camera import Camera
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_HOST, CONF_PORT, DOMAIN
from .coordinator import ZigmaStatusCoordinator
from .entity import ZigmaEntity

_CELL_COLORS = (
    (237, 243, 240),
    (64, 79, 74),
    (220, 228, 224),
    (255, 255, 255),
)
_PATH_COLOR = (20, 139, 119)
_DOCK_COLOR = (202, 83, 67)
_MAX_DIMENSION = 2048
_MAX_CELLS = 1_000_000
_CACHE_SECONDS = 20


def _png_chunk(kind: bytes, payload: bytes) -> bytes:
    """Encode one PNG chunk."""
    body = kind + payload
    return struct.pack(">I", len(payload)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)


def _paint_point(pixels: bytearray, width: int, height: int, x: int, y: int, color: tuple[int, int, int]) -> None:
    """Paint a clipped RGB pixel."""
    if 0 <= x < width and 0 <= y < height:
        offset = (y * width + x) * 3
        pixels[offset : offset + 3] = bytes(color)


def _paint_line(
    pixels: bytearray,
    width: int,
    height: int,
    x0: int,
    y0: int,
    x1: int,
    y1: int,
    color: tuple[int, int, int],
) -> None:
    """Paint a thin Bresenham line."""
    dx, dy = abs(x1 - x0), abs(y1 - y0)
    sx, sy = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1)
    error = dx - dy
    while True:
        _paint_point(pixels, width, height, x0, y0, color)
        if x0 == x1 and y0 == y1:
            break
        twice = 2 * error
        if twice > -dy:
            error -= dy
            x0 += sx
        if twice < dx:
            error += dx
            y0 += sy


def render_map_png(map_data: dict[str, Any]) -> bytes:
    """Render the documented row-major map cells and optional path/dock."""
    width, height, cells = map_data.get("width"), map_data.get("height"), map_data.get("cells")
    if (
        not isinstance(width, int)
        or not isinstance(height, int)
        or width < 1
        or height < 1
        or width > _MAX_DIMENSION
        or height > _MAX_DIMENSION
        or width * height > _MAX_CELLS
        or not isinstance(cells, list)
        or len(cells) != width * height
    ):
        raise ValueError("Map dimensions or cell data are invalid")

    pixels = bytearray(width * height * 3)
    for index, value in enumerate(cells):
        color = _CELL_COLORS[value] if isinstance(value, int) and 0 <= value < 4 else _CELL_COLORS[0]
        offset = index * 3
        pixels[offset : offset + 3] = bytes(color)

    path = map_data.get("path")
    if isinstance(path, list):
        points = [
            (round(point["x"]), round(point["y"]))
            for point in path[:20_000]
            if isinstance(point, dict)
            and isinstance(point.get("x"), (int, float))
            and isinstance(point.get("y"), (int, float))
        ]
        for first, second in zip(points, points[1:]):
            _paint_line(pixels, width, height, *first, *second, _PATH_COLOR)

    dock = map_data.get("dock")
    if (
        isinstance(dock, dict)
        and isinstance(dock.get("x"), (int, float))
        and isinstance(dock.get("y"), (int, float))
    ):
        dx, dy = round(dock["x"]), round(dock["y"])
        for step in range(-3, 4):
            _paint_point(pixels, width, height, dx + step, dy, _DOCK_COLOR)
            _paint_point(pixels, width, height, dx, dy + step, _DOCK_COLOR)

    scanlines = b"".join(
        b"\x00" + pixels[row * width * 3 : (row + 1) * width * 3]
        for row in range(height)
    )
    header = struct.pack(">2I5B", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", header)
        + _png_chunk(b"IDAT", zlib.compress(scanlines, level=6))
        + _png_chunk(b"IEND", b"")
    )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the on-demand map camera."""
    coordinator: ZigmaStatusCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [ZigmaMapCamera(coordinator, str(entry.data[CONF_HOST]), int(entry.data[CONF_PORT]))]
    )


class ZigmaMapCamera(ZigmaEntity, Camera):
    """Fetch a map only when Home Assistant requests an image."""

    _attr_name = "Map"
    _attr_content_type = "image/png"

    def __init__(self, coordinator: ZigmaStatusCoordinator, host: str, port: int) -> None:
        super().__init__(coordinator, host, port)
        self._attr_unique_id = f"{host}:{port}_map"
        self._cached_png: bytes | None = None
        self._cached_at = 0.0
        self._map_attributes: dict[str, Any] = {}
        self._last_error: str | None = None

    @property
    def should_poll(self) -> bool:
        """Do not poll map data in the background."""
        return False

    @property
    def available(self) -> bool:
        """Keep a cached image view available when the status route works."""
        return self.coordinator.last_update_success

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose map identity and API freshness hints without claiming live pose."""
        age = int(time.monotonic() - self._cached_at) if self._cached_png else None
        return {**self._map_attributes, "image_cache_age_s": age, "last_error": self._last_error}

    async def async_camera_image(self, width: int | None = None, height: int | None = None) -> bytes | None:
        """Fetch and render the map on demand, with a short image cache."""
        now = time.monotonic()
        if self._cached_png is not None and now - self._cached_at < _CACHE_SECONDS:
            return self._cached_png
        try:
            map_data = await self.coordinator.api.async_get_map()
            self._map_attributes = {
                key: map_data.get(key)
                for key in ("available", "map_id", "width", "height", "map_origin", "observed_at", "warning", "reset_pending")
                if key in map_data
            }
            self._map_attributes["cell_values_note"] = "API codes 0-3; individual cell meanings are not confirmed"
            if not map_data.get("available"):
                self._last_error = str(map_data.get("warning") or "Map is not currently available")
                return self._cached_png
            image = await self.hass.async_add_executor_job(render_map_png, map_data)
        except Exception as err:
            self._last_error = str(err)
            return self._cached_png
        self._cached_png = image
        self._cached_at = now
        self._last_error = None
        self.async_write_ha_state()
        return image
