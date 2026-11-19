# Zigma Spark 980 Free for Home Assistant

A local Home Assistant integration for the Zigma Spark 980 Free running the **v1.1-rc10** deployment. It connects to the robot's HTTP agent on your home network and adds native vacuum controls, sensors, schedules, and a live map.

## What you get

| Feature | Home Assistant entity or view |
| --- | --- |
| Start, resume, pause, and dock | Vacuum entity and individual action buttons |
| Choose suction strength for the next clean | Select entity with Quiet, Normal, and Maximum levels |
| See the full floor plan while the robot is working | Live camera with the driven route, dock, and robot marker |
| Check battery, status, errors, and telemetry freshness | Native sensors |
| Inspect or enable supported robot schedules | Schedule sensor and switches for schedules exposed by the API |

The included **Sparky** dashboard uses a responsive, map-first layout. It puts operating status and battery level above the map, with color-coded cleaning controls, suction selection, diagnostics, and schedule details alongside it.

## Install

1. In Home Assistant, open **HACS → Integrations → ⋮ → Custom repositories**.
2. Add `Figurix123/Zigma-980-Free-Home-Assistant-Integration` with category **Integration**.
3. Download **Zigma Free**, then restart Home Assistant.
4. Open **Settings → Devices & services → Add integration** and choose **Zigma Free**.
5. Enter the robot's local IP address, port `8765`, and web access key.

This is a custom HACS repository; it is not part of the default HACS catalog.

## Optional dashboard

The repository includes a reusable [map-first dashboard template](dashboards/sparky-dashboard.yaml). HACS installs the integration, but Home Assistant dashboards are stored separately and are **not installed automatically**.

1. Install the [`button-card` Lovelace card](https://github.com/custom-cards/button-card) through HACS or your Home Assistant frontend marketplace.
2. Find the entity IDs created for your robot under **Settings → Devices & services → Zigma Free**.
3. Create a new dashboard, open its raw configuration editor, and paste in `dashboards/sparky-dashboard.yaml`.
4. Replace every `replace_me` entity ID with the matching ID from your installation, then save.

The template uses standard Home Assistant cards for the map, status, battery, suction selector, diagnostics, and schedules. It uses `button-card` for the four large, colored actions; starting a clean and docking both ask for confirmation. The dashboard can be restyled without changing the integration itself.

## Live map

The camera follows the robot website's clean map style: a complete, centered floor plan, a fine dashed route, and clear dock and robot markers. Its frame expands to include reported route or robot coordinates outside the map grid. Fresh laser data is used to position the robot when it aligns with the active map; raw laser returns are not drawn over the floor plan.

The camera refreshes map and status data every 2.5 seconds and checks the laser endpoint every second while Home Assistant requests frames. The image is assembled from API snapshots; it is not a video stream. When the robot API only has a cached path position, the marker reflects that estimate and may not include a heading.

## How controls behave

- The vacuum entity exposes Home Assistant's standard vacuum controls. Separate buttons are available for Clean, Resume, Pause, and Dock.
- The suction selector saves the level for the **next full clean**. The API does not support changing suction power during an active clean.
- Schedule entities reflect schedules already exposed by the robot API. Home Assistant can enable or disable supported schedules; schedule creation and time editing are not available through this API.
- A successful command response means the robot accepted the request for processing. It does not confirm that the robot physically completed the action.

## Connection and privacy

- Home Assistant must be able to reach the robot on the local network. Remote access to Home Assistant alone does not provide a route to the robot's private IP address.
- API traffic uses plain HTTP on the local network. Keep the web access key private and do not expose the robot's API port to the internet.
- The integration communicates directly with the robot; it does not send robot data through a project cloud service.

## Current limits

Room and area cleaning, stop, locate, schedule editing, and changing suction power during a clean are not implemented. The API's cleaning-area value has no verified unit. Map and pose freshness depend on the snapshots the robot exposes.

## Source

Based on the public [Zigma Spark 980 Free v1.1-rc10 release](https://github.com/bultza/zigma-spark-980-free/releases/tag/v1.1-rc10).
