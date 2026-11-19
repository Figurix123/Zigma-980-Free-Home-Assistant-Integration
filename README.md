# Zigma Free for Home Assistant

Local Home Assistant integration for Zigma Spark 980 Free robots running the v1.1-rc10 deployment.

## Features

- Local HTTP connection to the robot on port `8765` using its web access key.
- Status polling every 10 seconds.
- Vacuum controls plus explicit Clean, Resume, Pause, and Dock buttons.
- A suction power selector (levels 1–3: Quiet, Normal, Full) used by the next full clean, with its choice saved in Home Assistant.
- Battery, cleaning time, raw cleaning-area value, native status, error, and telemetry freshness sensors.
- A near-live, website-style map camera with the complete map, dashed driven path, dock marker, and robot position. The square view keeps the full floor plan visible and expands to include a path or robot position just beyond the map grid. The camera uses a fresh, map-aligned laser pose when available, but does not paint raw laser returns over the floor plan. It requests `/api/laser` once per second and refreshes `/api/status` plus `/api/map` every 2.5 seconds, matching the robot website's cadence.
- A schedules diagnostic sensor and switches to enable or disable existing clean, dock, and song schedules. Schedule metadata refreshes every five minutes.

The command API confirms that a command was queued; it does not confirm that the robot physically completed it. The cleaning-area sensor intentionally has no unit because the API's native area unit has not been verified. Map cells use the same palette as the robot website; their physical occupancy meaning is not fully specified by the API. Live navigation poses are matched to the current map identity, dimensions, and origin. Map and pose freshness still depend on the robot API snapshots. This is a near-live image feed assembled from API snapshots, not HLS/WebRTC video. The API exposes suction power values 1–3 with a full-clean command; the selector sets the level for the next full clean and cannot change power mid-clean. Schedule switches only enable or disable an existing supported schedule; they do not run it immediately or edit its time.

## Install with HACS

1. In HACS, open the three-dot menu and choose **Custom repositories**.
2. Add `Figurix123/Zigma-980-Free-Home-Assistant-Integration` with category **Integration**.
3. Download **Zigma Free** in HACS and restart Home Assistant.
4. In **Settings → Devices & services**, add **Zigma Free**.
5. Enter the robot's LAN IP address, port `8765`, and web access key.

This repository is a custom HACS repository and is not part of the default HACS catalog.

## Requirements and limits

- The robot's local HTTP agent must be reachable from the Home Assistant host.
- API traffic uses plain HTTP on the local network; keep the access key private and do not expose port `8765` to the internet.
- Status, map, and live laser reads have been verified against a running robot. A queued command response still does not confirm that the robot physically completed that command.
- LiDAR controls, room cleaning, area cleaning, forbidden zones, locate, stop, schedule editing, and changing suction power during an active clean are not implemented.

## Source

Based on the public [Zigma Spark 980 Free v1.1-rc10 release](https://github.com/bultza/zigma-spark-980-free/releases/tag/v1.1-rc10).
