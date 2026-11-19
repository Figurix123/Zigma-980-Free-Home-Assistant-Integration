# Zigma Free for Home Assistant

Local Home Assistant integration for Zigma Spark 980 Free robots running the v1.1-rc10 deployment.

## Features

- Local HTTP connection to the robot on port `8765` using its web access key.
- Status polling every 10 seconds.
- Vacuum controls plus explicit Clean, Resume, Pause, and Dock buttons.
- Battery, cleaning time, raw cleaning-area value, native status, error, and telemetry freshness sensors.

The command API confirms that a command was queued; it does not confirm that the robot physically completed it. The cleaning-area sensor intentionally has no unit because the API's native area unit has not been verified. Maps and LiDAR are not polled.

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
- Map display, LiDAR, room cleaning, area cleaning, forbidden zones, locate, stop, and live fan-speed changes are not implemented.

## Source

Based on the public [Zigma Spark 980 Free v1.1-rc10 release](https://github.com/bultza/zigma-spark-980-free/releases/tag/v1.1-rc10).
