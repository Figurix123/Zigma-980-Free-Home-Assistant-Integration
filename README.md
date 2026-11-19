# Zigma Spark 980 Free for Home Assistant

A local Home Assistant integration for the Zigma Spark 980 Free running the **v1.1-rc10** deployment. It connects to the robot's HTTP agent on your home network and adds native vacuum controls, sensors, schedules, and a live map.

## What you get

| Feature | Home Assistant entity or view |
| --- | --- |
| Start, resume, pause, and dock | Vacuum entity and individual action buttons |
| Choose suction strength for the next clean | Select entity with Quiet, Normal, and Maximum levels |
| Set the robot's speaker volume | Number entity with a 0–100 slider |
| See the full floor plan while the robot is working | Tightly framed transparent PNG with route, dock, and robot marker |
| Check battery, status, errors, and telemetry freshness | Native sensors |
| Inspect or enable supported robot schedules | Schedule sensor and switches for schedules exposed by the API |

The included dashboard has a map-first **Sparky** view for live status and controls, plus a **Details** view for diagnostics and schedules. This keeps the frequent actions together and puts secondary information one tap away.

## Install

1. In Home Assistant, open **HACS → Integrations → ⋮ → Custom repositories**.
2. Add `Figurix123/Zigma-980-Free-Home-Assistant-Integration` with category **Integration**.
3. Download **Zigma Free**, then restart Home Assistant.
4. Open **Settings → Devices & services → Add integration** and choose **Zigma Free**.
5. Enter the robot's local IP address, port `8765`, and web access key.

This is a custom HACS repository; it is not part of the default HACS catalog.

## Optional dashboard

The repository includes a reusable [map-first dashboard template](dashboards/sparky-dashboard.yaml). HACS installs the integration, but Home Assistant dashboards are stored separately and are **not installed automatically**.

1. Install the [`button-card`](https://github.com/custom-cards/button-card) and [`auto-entities`](https://github.com/thomasloven/lovelace-auto-entities) Lovelace cards through HACS or your Home Assistant frontend marketplace.
2. Find the entity IDs created for your robot under **Settings → Devices & services → Zigma Free**.
3. Create a new dashboard, open its raw configuration editor, and paste in `dashboards/sparky-dashboard.yaml`.
4. Replace every `replace_me` entity ID with the matching ID from your installation, then save.

The template uses standard Home Assistant cards for the map, status, battery, suction selector, speaker volume, and diagnostics. Its map overlays clearly labeled Pause and Dock controls; the map darkens automatically when Home Assistant is in dark mode. `button-card` styles the four large, colored actions; starting a clean and docking both ask for confirmation. `auto-entities` adds schedule switches automatically when the robot exposes schedules, so the dashboard does not need a hard-coded entity ID for each one. The dashboard can be restyled without changing the integration itself.

For a live map on an existing dashboard, copy the [Sparky live section](dashboards/sparky-live-section.yaml) into that dashboard view's `sections` list. It appears while the vacuum is cleaning or returning to its dock, overlays clearly labeled Pause and Dock buttons on the map, and groups status, battery, and cleaning time beside it on wider screens. The map keeps the generated PNG's portrait aspect ratio so the full floor plan stays visible as the dashboard changes width.

## Live map

The camera follows the robot website's clean map style: a complete floor plan, a fine dashed route, and clear dock and robot markers. The PNG is cropped to the map and reported overlays, with transparent unknown areas instead of a large dotted white border. Its frame expands to include route or robot coordinates outside the map grid. Fresh laser data is used to position the robot when it aligns with the active map; raw laser returns are not drawn over the floor plan.

The camera refreshes map and status data every 2.5 seconds and checks the laser endpoint every second while Home Assistant requests frames. The image is assembled from API snapshots; it is not a video stream. When the robot API only has a cached path position, the marker reflects that estimate and may not include a heading.

## How controls behave

- The vacuum entity exposes Home Assistant's standard vacuum controls. Separate buttons are available for Clean, Resume, Pause, and Dock.
- The suction selector saves the level for the **next full clean**. The API does not support changing suction power during an active clean.
- The speaker-volume number changes the robot's voice volume using its local settings API.
- Schedule entities reflect schedules already exposed by the robot API. This integration can enable or disable supported schedules; create and edit schedules through the robot's web interface.
- A successful command response means the robot accepted the request for processing. It does not confirm that the robot physically completed the action.

## Connection and privacy

- Home Assistant must be able to reach the robot on the local network. Remote access to Home Assistant alone does not provide a route to the robot's private IP address.
- API traffic uses plain HTTP on the local network. Keep the web access key private and do not expose the robot's API port to the internet.
- The integration communicates directly with the robot; it does not send robot data through a project cloud service.

## Current limits

This integration does not yet expose saved-map management, map-based area selection, direct navigation to a point, cleaning-history reports, voice-prompt files, or schedule creation and editing. Suction strength cannot be changed during an active clean. Pause is the supported stop-like action in the robot API. Live map detail and robot-position accuracy depend on the snapshots the robot currently reports.

## Source

Based on the public [Zigma Spark 980 Free v1.1-rc10 release](https://github.com/bultza/zigma-spark-980-free/releases/tag/v1.1-rc10).
