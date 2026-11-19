# Zigma Free for Home Assistant

Local Home Assistant integration for Zigma Spark 980 Free robots running the v1.1-rc10 deployment.

## Features

- Local HTTP connection to the robot on port `8765` using its web access key.
- Status polling every 10 seconds.
- Vacuum controls plus explicit Clean, Resume, Pause, and Dock buttons.
- Battery, cleaning time, raw cleaning-area value, native status, error, and telemetry freshness sensors.
- A near-live map camera with the robot pose, current 360-degree laser returns, path, and dock marker. It requests `/api/laser` once per second and refreshes `/api/status` plus `/api/map` every 2.5 seconds, matching the robot website's cadence. Home Assistant serves the frames as a one-frame-per-second MJPEG-style image stream.
- A schedules diagnostic sensor and switches to enable or disable existing clean, dock, and song schedules. Schedule metadata refreshes every five minutes.

The command API confirms that a command was queued; it does not confirm that the robot physically completed it. The cleaning-area sensor intentionally has no unit because the API's native area unit has not been verified. Map cells use the same palette as the robot website; their physical occupancy meaning is not fully specified by the API. Laser points and robot pose are drawn only when the live pose matches the current map identity, dimensions, and origin. This is a near-live image feed assembled from API snapshots, not HLS/WebRTC video. Schedule switches only enable or disable an existing supported schedule; they do not run it immediately or edit its time.

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
- API behavior was derived from the v1.1-rc10 release and matching source tag. This integration has not yet been runtime-tested against a physical robot.
- LiDAR, room cleaning, area cleaning, forbidden zones, locate, stop, schedule editing, and live fan-speed changes are not implemented.

## Source

Based on the public [Zigma Spark 980 Free v1.1-rc10 release](https://github.com/bultza/zigma-spark-980-free/releases/tag/v1.1-rc10).
