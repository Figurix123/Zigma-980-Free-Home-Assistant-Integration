"""Live map camera with the robot's laser scan overlaid."""

from __future__ import annotations

import asyncio
import math
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
    (250, 250, 245),
    (184, 195, 175),
    (217, 189, 139),
    (250, 250, 245),
)
_PATH_COLOR = (180, 161, 129)
_DOCK_COLOR = (129, 149, 114)
_LASER_COLOR = (18, 124, 129)
_STALE_LASER_COLOR = (136, 136, 136)
_ROBOT_COLOR = (72, 123, 152)
_MAX_DIMENSION = 2048
_MAX_CELLS = 1_000_000
_IMAGE_CACHE_SECONDS = 0.5
_LASER_REFRESH_SECONDS = 1.0
_MAP_REFRESH_SECONDS = 2.5
_STATUS_REFRESH_SECONDS = 2.5
_LASER_MAX_AGE_MS = 3000


def _png_chunk(kind: bytes, payload: bytes) -> bytes:
    """Encode one PNG chunk."""
    body = kind + payload
    return struct.pack(">I", len(payload)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)


def _paint_point(
    pixels: bytearray,
    width: int,
    height: int,
    x: int,
    y: int,
    color: tuple[int, int, int],
) -> None:
    """Paint a clipped RGB pixel."""
    if 0 <= x < width and 0 <= y < height:
        offset = (y * width + x) * 3
        pixels[offset : offset + 3] = bytes(color)


def _paint_disk(
    pixels: bytearray,
    width: int,
    height: int,
    x: int,
    y: int,
    radius: int,
    color: tuple[int, int, int],
) -> None:
    """Paint a small filled circle."""
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            if dx * dx + dy * dy <= radius * radius:
                _paint_point(pixels, width, height, x + dx, y + dy, color)


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


def _finite_number(value: Any) -> bool:
    """Return whether a value is a finite real number, excluding booleans."""
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _pose_matches_map(map_data: dict[str, Any], pose: Any) -> bool:
    """Check that a pose is expressed in this exact map grid."""
    if not isinstance(pose, dict) or not map_data.get("map_id"):
        return False
    if str(pose.get("map_id")) != str(map_data.get("map_id")):
        return False
    if pose.get("width") != map_data.get("width") or pose.get("height") != map_data.get("height"):
        return False
    pose_origin, map_origin = pose.get("map_origin"), map_data.get("map_origin")
    if (
        not isinstance(pose_origin, list)
        or not isinstance(map_origin, list)
        or len(pose_origin) != 2
        or len(map_origin) != 2
        or pose_origin != map_origin
    ):
        return False
    width, height = map_data.get("width"), map_data.get("height")
    if (
        not isinstance(width, int)
        or isinstance(width, bool)
        or not isinstance(height, int)
        or isinstance(height, bool)
    ):
        return False
    return (
        _finite_number(pose.get("x"))
        and _finite_number(pose.get("y"))
        and _finite_number(pose.get("heading"))
        and 0 <= pose["x"] < width
        and 0 <= pose["y"] < height
    )


def _fresh_laser(laser_data: Any, received_at: float | None, now: float) -> bool:
    """Apply the same freshness and shape checks as the robot's web UI."""
    if not isinstance(laser_data, dict) or laser_data.get("available") is not True or received_at is None:
        return False
    ranges = laser_data.get("ranges_mm")
    read_age = laser_data.get("read_age_ms")
    if (
        not isinstance(ranges, list)
        or len(ranges) != 360
        or any(not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 100_000 for value in ranges)
        or not _finite_number(read_age)
        or read_age < 0
    ):
        return False
    age = read_age + max(0.0, (now - received_at) * 1000)
    return age <= _LASER_MAX_AGE_MS


def _status_pose(map_data: dict[str, Any], status_data: dict[str, Any], now: float) -> dict[str, Any] | None:
    """Return a recent status pose that still matches the current map."""
    if status_data.get("working_status") == "Relocation" or status_data.get("map_reset_pending"):
        return None
    pose = status_data.get("navigation_pose")
    if not _pose_matches_map(map_data, pose):
        return None
    if pose.get("kind") != "navigation_pose_cache" or pose.get("frame") != "map_grid":
        return None
    cache_read_at = pose.get("cache_read_at")
    if not _finite_number(cache_read_at):
        return None
    age = now - cache_read_at
    return pose if 0 <= age <= 15 else None


def render_map_png(
    map_data: dict[str, Any],
    status_data: dict[str, Any] | None = None,
    laser_data: dict[str, Any] | None = None,
    laser_received_at: float | None = None,
) -> bytes:
    """Render the map, fresh laser returns, and only safely aligned robot pose."""
    width, height, cells = map_data.get("width"), map_data.get("height"), map_data.get("cells")
    if (
        map_data.get("available") is not True
        or not isinstance(width, int)
        or isinstance(width, bool)
        or not isinstance(height, int)
        or isinstance(height, bool)
        or width < 1
        or height < 1
        or width > _MAX_DIMENSION
        or height > _MAX_DIMENSION
        or width * height > _MAX_CELLS
        or not isinstance(cells, list)
        or len(cells) != width * height
    ):
        raise ValueError(str(map_data.get("warning") or "Map dimensions or cell data are invalid"))

    status = status_data or {}
    pixels = bytearray(_CELL_COLORS[0] * (width * height))
    for index, value in enumerate(cells):
        color = _CELL_COLORS[value] if isinstance(value, int) and not isinstance(value, bool) and 0 <= value < 4 else _CELL_COLORS[0]
        offset = index * 3
        pixels[offset : offset + 3] = bytes(color)

    path = map_data.get("path")
    if isinstance(path, list):
        previous: tuple[int, int] | None = None
        for point in path[:5_000]:
            if not (
                isinstance(point, dict)
                and _finite_number(point.get("x"))
                and _finite_number(point.get("y"))
                and 0 <= point["x"] < width
                and 0 <= point["y"] < height
            ):
                previous = None
                continue
            current = (round(point["x"]), round(point["y"]))
            if previous is not None:
                _paint_line(pixels, width, height, *previous, *current, _PATH_COLOR)
            previous = current

    dock = map_data.get("dock")
    if isinstance(dock, dict) and _finite_number(dock.get("x")) and _finite_number(dock.get("y")):
        dock_x, dock_y = round(dock["x"]), round(dock["y"])
        for step in range(-3, 4):
            _paint_point(pixels, width, height, dock_x + step, dock_y, _DOCK_COLOR)
            _paint_point(pixels, width, height, dock_x, dock_y + step, _DOCK_COLOR)

    now_monotonic = time.monotonic()
    laser_fresh = _fresh_laser(laser_data, laser_received_at, now_monotonic)
    laser_pose = laser_data.get("navigation_pose") if isinstance(laser_data, dict) else None
    overlay_ready = (
        laser_fresh
        and not map_data.get("reset_pending")
        and not status.get("map_reset_pending")
        and status.get("working_status") != "Relocation"
        and _pose_matches_map(map_data, laser_pose)
        and _finite_number(laser_pose.get("resolution_m"))
        and 0.001 <= laser_pose["resolution_m"] <= 1
    )

    if overlay_ready:
        resolution = laser_pose["resolution_m"]
        heading = laser_pose["heading"]
        change_age = laser_data.get("change_age_ms")
        elapsed_ms = max(0.0, (now_monotonic - (laser_received_at or now_monotonic)) * 1000)
        changing = _finite_number(change_age) and change_age >= 0 and change_age + elapsed_ms <= _LASER_MAX_AGE_MS
        laser_color = _LASER_COLOR if changing else _STALE_LASER_COLOR
        for index, distance_mm in enumerate(laser_data["ranges_mm"]):
            if distance_mm == 0:
                continue
            distance_cells = distance_mm / 1000 / resolution
            angle = index * math.pi / 180 + heading
            point_x = round(laser_pose["x"] + distance_cells * math.cos(angle))
            point_y = round(laser_pose["y"] + distance_cells * math.sin(angle))
            _paint_disk(pixels, width, height, point_x, point_y, 1, laser_color)

    pose = laser_pose if overlay_ready else _status_pose(map_data, status, time.time())
    if pose is not None:
        robot_x, robot_y = round(pose["x"]), round(pose["y"])
        if _finite_number(pose.get("resolution_m")) and 0.001 <= pose["resolution_m"] <= 1:
            arrow_length = max(5, min(12, round(0.3 / pose["resolution_m"])))
        else:
            arrow_length = 7
        arrow_x = round(robot_x + arrow_length * math.cos(pose["heading"]))
        arrow_y = round(robot_y + arrow_length * math.sin(pose["heading"]))
        _paint_line(pixels, width, height, robot_x, robot_y, arrow_x, arrow_y, _ROBOT_COLOR)
        _paint_disk(pixels, width, height, robot_x, robot_y, 3, _ROBOT_COLOR)

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
    """Set up the live map camera."""
    coordinator: ZigmaStatusCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [ZigmaMapCamera(coordinator, str(entry.data[CONF_HOST]), int(entry.data[CONF_PORT]))]
    )


class ZigmaMapCamera(ZigmaEntity, Camera):
    """Render an MJPEG-style feed from live robot API snapshots."""

    _attr_name = "Map"
    _attr_frame_interval = _LASER_REFRESH_SECONDS

    def __init__(self, coordinator: ZigmaStatusCoordinator, host: str, port: int) -> None:
        # Camera is a sibling of CoordinatorEntity in the MRO, so initialize
        # both base classes explicitly.
        ZigmaEntity.__init__(self, coordinator, host, port)
        Camera.__init__(self)
        self.content_type = "image/png"
        self._attr_unique_id = f"{host}:{port}_map"
        self._image_lock = asyncio.Lock()
        self._cached_png: bytes | None = None
        self._cached_at = 0.0
        self._status_checked_at = 0.0
        self._map_checked_at = 0.0
        self._laser_checked_at = 0.0
        self._laser_received_at: float | None = None
        self._status_data: dict[str, Any] = dict(coordinator.data or {})
        self._map_data: dict[str, Any] | None = None
        self._laser_data: dict[str, Any] | None = None
        self._map_attributes: dict[str, Any] = {}
        self._last_error: str | None = None

    @property
    def should_poll(self) -> bool:
        """Fetch map and scan data only while Home Assistant requests frames."""
        return False

    @property
    def available(self) -> bool:
        """Keep the image entity tied to the lightweight status connection."""
        return self.coordinator.last_update_success

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose stable map identity and live-scan availability."""
        age = int(time.monotonic() - self._cached_at) if self._cached_png else None
        return {**self._map_attributes, "image_cache_age_s": age, "last_error": self._last_error}

    async def _async_refresh_robot_data(self) -> None:
        """Poll laser at 1 Hz and status/map at the website's 2.5-second cadence."""
        now = time.monotonic()
        pending: list[tuple[str, Any]] = []
        if now - self._status_checked_at >= _STATUS_REFRESH_SECONDS:
            self._status_checked_at = now
            pending.append(("status", self.coordinator.api.async_get_status()))
        if now - self._map_checked_at >= _MAP_REFRESH_SECONDS:
            self._map_checked_at = now
            pending.append(("map", self.coordinator.api.async_get_map()))
        if now - self._laser_checked_at >= _LASER_REFRESH_SECONDS:
            self._laser_checked_at = now
            pending.append(("laser", self.coordinator.api.async_get_laser()))
        if not pending:
            return

        results = await asyncio.gather(*(request for _, request in pending), return_exceptions=True)
        errors: list[str] = []
        for (name, _), result in zip(pending, results, strict=True):
            if isinstance(result, asyncio.CancelledError):
                raise result
            if isinstance(result, Exception):
                errors.append(f"{name}: {result}")
                continue
            if name == "status":
                self._status_data = result
            elif name == "map":
                self._map_data = result
            else:
                self._laser_data = result
                self._laser_received_at = time.monotonic()
        self._last_error = "; ".join(errors)[:300] if errors else None

    def _update_map_attributes(self) -> None:
        """Update only stable camera attributes so 1 Hz frames do not pollute history."""
        map_data = self._map_data or {}
        now = time.monotonic()
        laser_fresh = _fresh_laser(self._laser_data, self._laser_received_at, now)
        laser_pose = self._laser_data.get("navigation_pose") if isinstance(self._laser_data, dict) else None
        aligned = (
            laser_fresh
            and bool(map_data)
            and _pose_matches_map(map_data, laser_pose)
            and _finite_number(laser_pose.get("resolution_m"))
            and 0.001 <= laser_pose["resolution_m"] <= 1
            and not map_data.get("reset_pending")
            and not self._status_data.get("map_reset_pending")
            and self._status_data.get("working_status") != "Relocation"
        )
        self._map_attributes = {
            key: map_data[key]
            for key in ("map_id", "width", "height", "map_origin", "observed_at", "warning", "reset_pending")
            if key in map_data
        }
        self._map_attributes.update(
            {
                "cell_values_note": "API codes 0-3 are drawn using the robot web UI palette",
                "live_laser_available": laser_fresh,
                "map_overlay_aligned": bool(aligned),
                "laser_refresh_s": _LASER_REFRESH_SECONDS,
                "map_refresh_s": _MAP_REFRESH_SECONDS,
            }
        )

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        """Return a fresh map frame, or the last good frame during a brief outage."""
        now = time.monotonic()
        if self._cached_png is not None and now - self._cached_at < _IMAGE_CACHE_SECONDS:
            return self._cached_png

        async with self._image_lock:
            now = time.monotonic()
            if self._cached_png is not None and now - self._cached_at < _IMAGE_CACHE_SECONDS:
                return self._cached_png
            previous_attributes = self._map_attributes.copy()
            previous_error = self._last_error
            await self._async_refresh_robot_data()
            self._update_map_attributes()

            map_data = self._map_data or {}
            reset_pending = map_data.get("reset_pending") or self._status_data.get("map_reset_pending")
            if reset_pending:
                self._cached_png = None
                self._last_error = str(map_data.get("warning") or "Waiting for the robot to finish changing maps")
                if previous_attributes != self._map_attributes or previous_error != self._last_error:
                    self.async_write_ha_state()
                return None

            if map_data.get("available") is not True:
                if not self._last_error:
                    self._last_error = str(map_data.get("warning") or "The robot has no available map")
                if previous_attributes != self._map_attributes or previous_error != self._last_error:
                    self.async_write_ha_state()
                return self._cached_png

            try:
                image = await self.hass.async_add_executor_job(
                    render_map_png,
                    map_data,
                    self._status_data,
                    self._laser_data,
                    self._laser_received_at,
                )
            except Exception as err:
                self._last_error = str(err)
                if previous_attributes != self._map_attributes or previous_error != self._last_error:
                    self.async_write_ha_state()
                return self._cached_png

            self._cached_png = image
            self._cached_at = time.monotonic()
            if previous_attributes != self._map_attributes or previous_error != self._last_error:
                self.async_write_ha_state()
            return image
