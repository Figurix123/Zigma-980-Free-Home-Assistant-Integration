"""Website-style live map camera for the robot."""

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

_CELL_COLORS: tuple[tuple[int, int, int] | None, ...] = (
    (250, 250, 245),
    (184, 195, 175),
    (217, 189, 139),
    None,
)
_BACKGROUND_COLOR = (242, 243, 237)
_BACKGROUND_DOT_COLOR = (188, 197, 181)
_PATH_COLOR = (180, 161, 129)
_DOCK_COLOR = (129, 149, 114)
_NAV_ROBOT_COLOR = (72, 123, 152)
_ROBOT_COLOR = (67, 107, 83)
_CANVAS_SIZE = 448
_IMAGE_SCALE = 2
_CANVAS_PADDING = 24
_MAX_DIMENSION = 2048
_MAX_CELLS = 1_000_000
_MAX_COORDINATE = 1_000_000
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


def _blend_point(
    pixels: bytearray,
    width: int,
    height: int,
    x: int,
    y: int,
    color: tuple[int, int, int],
    alpha: int,
) -> None:
    """Blend one clipped RGB pixel over the map-stage background."""
    if 0 <= x < width and 0 <= y < height:
        offset = (y * width + x) * 3
        inverse = 255 - alpha
        pixels[offset] = (pixels[offset] * inverse + color[0] * alpha) // 255
        pixels[offset + 1] = (pixels[offset + 1] * inverse + color[1] * alpha) // 255
        pixels[offset + 2] = (pixels[offset + 2] * inverse + color[2] * alpha) // 255


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


def _paint_brush(
    pixels: bytearray,
    width: int,
    height: int,
    x: int,
    y: int,
    radius: int,
    color: tuple[int, int, int],
) -> None:
    """Paint a small round brush centered at floating-point coordinates."""
    _paint_disk(pixels, width, height, round(x), round(y), radius, color)


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


def _paint_dashed_segment(
    pixels: bytearray,
    width: int,
    height: int,
    start: tuple[float, float],
    end: tuple[float, float],
    color: tuple[int, int, int],
    phase: float,
) -> float:
    """Draw the website's 3px / 4px dashed path and carry its dash phase."""
    dx, dy = end[0] - start[0], end[1] - start[1]
    length = math.hypot(dx, dy)
    if length == 0:
        return phase
    steps = max(1, math.ceil(length))
    for step in range(steps + 1):
        distance = length * step / steps
        if (phase + distance) % 14 < 6:
            ratio = step / steps
            _paint_brush(
                pixels,
                width,
                height,
                start[0] + dx * ratio,
                start[1] + dy * ratio,
                1,
                color,
            )
    return (phase + length) % 14


def _fill_rect(
    pixels: bytearray,
    width: int,
    height: int,
    x0: int,
    y0: int,
    x1: int,
    y1: int,
    color: tuple[int, int, int],
) -> None:
    """Fill a clipped rectangle with inclusive start and exclusive end."""
    x0, x1 = max(0, x0), min(width, x1)
    y0, y1 = max(0, y0), min(height, y1)
    if x0 >= x1 or y0 >= y1:
        return
    row = bytes(color) * (x1 - x0)
    for y in range(y0, y1):
        offset = (y * width + x0) * 3
        pixels[offset : offset + len(row)] = row


def _paint_background(pixels: bytearray, width: int, height: int) -> None:
    """Paint the light, subtly dotted background used by the robot website."""
    pixels[:] = bytes(_BACKGROUND_COLOR) * (width * height)
    dot = _BACKGROUND_DOT_COLOR
    spacing = 26 * _IMAGE_SCALE
    radius = max(1, _IMAGE_SCALE)
    for y in range(spacing // 2, height, spacing):
        for x in range(spacing // 2, width, spacing):
            for dy in range(-radius, radius + 1):
                for dx in range(-radius, radius + 1):
                    if dx * dx + dy * dy <= radius * radius:
                        _blend_point(pixels, width, height, x + dx, y + dy, dot, 72)


def _paint_rounded_rect(
    pixels: bytearray,
    width: int,
    height: int,
    x: int,
    y: int,
    rect_width: int,
    rect_height: int,
    radius: int,
    color: tuple[int, int, int],
) -> None:
    """Fill a small rounded rectangle."""
    for py in range(y, y + rect_height):
        for px in range(x, x + rect_width):
            cx = min(max(px, x + radius), x + rect_width - radius - 1)
            cy = min(max(py, y + radius), y + rect_height - radius - 1)
            if (px - cx) ** 2 + (py - cy) ** 2 <= radius * radius:
                _paint_point(pixels, width, height, px, py, color)


def _fill_polygon(
    pixels: bytearray,
    width: int,
    height: int,
    points: list[tuple[float, float]],
    color: tuple[int, int, int],
    alpha: int,
) -> None:
    """Fill a small polygon by scanline, blending over the map background."""
    if len(points) < 3:
        return
    y_start = max(0, math.floor(min(point[1] for point in points)))
    y_end = min(height, math.ceil(max(point[1] for point in points)))
    for y in range(y_start, y_end):
        scan_y = y + 0.5
        intersections: list[float] = []
        for index, point in enumerate(points):
            following = points[(index + 1) % len(points)]
            if (point[1] <= scan_y < following[1]) or (following[1] <= scan_y < point[1]):
                ratio = (scan_y - point[1]) / (following[1] - point[1])
                intersections.append(point[0] + ratio * (following[0] - point[0]))
        intersections.sort()
        for index in range(0, len(intersections) - 1, 2):
            start = max(0, math.ceil(intersections[index]))
            end = min(width, math.ceil(intersections[index + 1]))
            for x in range(start, end):
                _blend_point(pixels, width, height, x, y, color, alpha)


def _as_map_point(value: Any) -> dict[str, Any] | None:
    """Return a finite map-coordinate object from an API position value."""
    if not isinstance(value, dict) or not _finite_number(value.get("x")) or not _finite_number(value.get("y")):
        return None
    if abs(value["x"]) > _MAX_COORDINATE or abs(value["y"]) > _MAX_COORDINATE:
        return None
    return value


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
    """Render the full map and a website-style path, dock, and robot marker."""
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

    navigation = laser_pose if overlay_ready else _status_pose(map_data, status, time.time())
    reported_position = _as_map_point(map_data.get("position"))
    estimate = _as_map_point(map_data.get("position_estimate"))
    if estimate is not None:
        received_at = estimate.get("received_at")
        age = time.time() - received_at if _finite_number(received_at) else math.inf
        if not 0 <= age <= 6:
            estimate = None
    endpoint = _as_map_point(map_data.get("path_endpoint"))
    pose = navigation or reported_position or estimate or endpoint

    path: list[dict[str, Any]] = []
    raw_path = map_data.get("path")
    if isinstance(raw_path, list):
        path = [point for value in raw_path[:5_000] if (point := _as_map_point(value)) is not None]

    dock = _as_map_point(map_data.get("dock"))
    zones = map_data.get("zones") if isinstance(map_data.get("zones"), list) else []

    # Keep the complete cell grid in frame, then expand its world bounds when
    # the path, dock, or aligned robot pose extends beyond the returned grid.
    xs = [0.0, float(width)]
    ys = [0.0, float(height)]
    for point in [*path, dock, pose]:
        if point is not None:
            xs.append(float(point["x"]))
            ys.append(float(point["y"]))
    zone_polygons: list[tuple[list[tuple[float, float]], tuple[int, int, int], int]] = []
    for zone in zones:
        if not isinstance(zone, dict):
            continue
        points = zone.get("points")
        if isinstance(points, list) and 3 <= len(points) <= 32:
            polygon = [
                (float(point["x"]), float(point["y"]))
                for value in points
                if (point := _as_map_point(value)) is not None
            ]
            if len(polygon) == len(points):
                color = (199, 154, 81) if zone.get("can_clean") else (186, 109, 93)
                zone_polygons.append((polygon, color, 51))
                xs.extend(point[0] for point in polygon)
                ys.extend(point[1] for point in polygon)
        elif all(_finite_number(zone.get(key)) for key in ("x", "y", "width", "height")):
            x, y = float(zone["x"]), float(zone["y"])
            zone_width, zone_height = float(zone["width"]), float(zone["height"])
            if max(abs(x), abs(y), abs(zone_width), abs(zone_height)) <= _MAX_COORDINATE:
                polygon = [(x, y), (x + zone_width, y), (x + zone_width, y + zone_height), (x, y + zone_height)]
                zone_polygons.append((polygon, (196, 126, 108), 28))
                xs.extend(point[0] for point in polygon)
                ys.extend(point[1] for point in polygon)

    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    span_x, span_y = max_x - min_x, max_y - min_y
    if span_x <= 0 or span_y <= 0 or max(span_x, span_y) > _MAX_COORDINATE:
        raise ValueError("Map overlays are outside the supported coordinate range")

    image_width = image_height = _CANVAS_SIZE * _IMAGE_SCALE
    pixels = bytearray(image_width * image_height * 3)
    _paint_background(pixels, image_width, image_height)
    scale = min(
        (_CANVAS_SIZE - 2 * _CANVAS_PADDING) / span_x,
        (_CANVAS_SIZE - 2 * _CANVAS_PADDING) / span_y,
    )
    left = (_CANVAS_SIZE - span_x * scale) / 2 - min_x * scale
    top = (_CANVAS_SIZE - span_y * scale) / 2 - min_y * scale

    def to_pixel(x: float, y: float) -> tuple[float, float]:
        return ((left + x * scale) * _IMAGE_SCALE, (top + y * scale) * _IMAGE_SCALE)

    map_left, map_top = to_pixel(0, 0)
    cell_scale = scale * _IMAGE_SCALE
    if cell_scale < 1:
        # Nearest-neighbour downsample when a map cell is smaller than a pixel.
        x_start = max(0, math.floor(map_left))
        x_end = min(image_width, math.ceil(map_left + width * cell_scale))
        y_start = max(0, math.floor(map_top))
        y_end = min(image_height, math.ceil(map_top + height * cell_scale))
        for py in range(y_start, y_end):
            grid_y = min(height - 1, max(0, int((py + 0.5 - map_top) / cell_scale)))
            for px in range(x_start, x_end):
                grid_x = min(width - 1, max(0, int((px + 0.5 - map_left) / cell_scale)))
                value = cells[grid_y * width + grid_x]
                color = _CELL_COLORS[value] if isinstance(value, int) and not isinstance(value, bool) and 0 <= value < len(_CELL_COLORS) else None
                if color is not None:
                    _paint_point(pixels, image_width, image_height, px, py, color)
    else:
        for grid_y in range(height):
            for grid_x in range(width):
                value = cells[grid_y * width + grid_x]
                color = _CELL_COLORS[value] if isinstance(value, int) and not isinstance(value, bool) and 0 <= value < len(_CELL_COLORS) else None
                if color is None:
                    continue
                x0, y0 = to_pixel(grid_x, grid_y)
                x1, y1 = to_pixel(grid_x + 1, grid_y + 1)
                _fill_rect(
                    pixels,
                    image_width,
                    image_height,
                    math.floor(x0),
                    math.floor(y0),
                    math.ceil(x1),
                    math.ceil(y1),
                    color,
                )

    # Match the web app: the path is dashed, thin, and sits on top of the map.
    previous: tuple[float, float] | None = None
    dash_phase = 0.0
    for point in raw_path[:5_000] if isinstance(raw_path, list) else []:
        valid_point = _as_map_point(point)
        if valid_point is None:
            previous = None
            dash_phase = 0.0
            continue
        current = to_pixel(float(valid_point["x"]), float(valid_point["y"]))
        if previous is not None:
            dash_phase = _paint_dashed_segment(pixels, image_width, image_height, previous, current, _PATH_COLOR, dash_phase)
        previous = current

    for polygon, color, fill_alpha in zone_polygons:
        transformed = [to_pixel(x, y) for x, y in polygon]
        _fill_polygon(pixels, image_width, image_height, transformed, color, fill_alpha)
        for index, start in enumerate(transformed):
            end = transformed[(index + 1) % len(transformed)]
            _paint_line(pixels, image_width, image_height, round(start[0]), round(start[1]), round(end[0]), round(end[1]), color)

    if dock is not None:
        dock_x, dock_y = to_pixel(float(dock["x"]), float(dock["y"]))
        dock_width, dock_height = 12 * _IMAGE_SCALE, 9 * _IMAGE_SCALE
        x, y = round(dock_x - dock_width / 2), round(dock_y - dock_height / 2)
        _paint_rounded_rect(pixels, image_width, image_height, x, y, dock_width, dock_height, 2 * _IMAGE_SCALE, _DOCK_COLOR)
        _paint_line(pixels, image_width, image_height, round(dock_x - 3 * _IMAGE_SCALE), round(dock_y), round(dock_x + 3 * _IMAGE_SCALE), round(dock_y), (247, 248, 242))

    if pose is not None:
        robot_x, robot_y = to_pixel(float(pose["x"]), float(pose["y"]))
        center_x, center_y = round(robot_x), round(robot_y)
        nav_color = navigation is not None
        robot_color = _NAV_ROBOT_COLOR if nav_color else _ROBOT_COLOR if reported_position is not None or estimate is not None else _PATH_COLOR
        # A faint halo, white outline, and filled marker match the web view.
        for py in range(center_y - 20, center_y + 21):
            for px in range(center_x - 20, center_x + 21):
                distance = (px - center_x) ** 2 + (py - center_y) ** 2
                if 18**2 <= distance <= 20**2:
                    _blend_point(pixels, image_width, image_height, px, py, (69, 106, 68), 38)
        _paint_disk(pixels, image_width, image_height, center_x, center_y, 14, (255, 255, 255))
        _paint_disk(pixels, image_width, image_height, center_x, center_y, 11, robot_color)
        if navigation is not None and _finite_number(navigation.get("heading")):
            heading_length = 18 * _IMAGE_SCALE
            heading_x = round(robot_x + heading_length * math.cos(navigation["heading"]))
            heading_y = round(robot_y + heading_length * math.sin(navigation["heading"]))
            _paint_line(pixels, image_width, image_height, center_x, center_y, heading_x, heading_y, _NAV_ROBOT_COLOR)

    scanlines = b"".join(
        b"\x00" + pixels[row * image_width * 3 : (row + 1) * image_width * 3]
        for row in range(image_height)
    )
    header = struct.pack(">2I5B", image_width, image_height, 8, 2, 0, 0, 0)
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
                "cell_values_note": "Map colors match the robot web UI; unknown cells are transparent over the map background",
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
