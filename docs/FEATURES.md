# Entities, discovery and detection behavior

## Entities and dashboard icons

For a device named `Driveway`, HA normally generates these IDs. Existing entity names can cause suffixes, so check the device page and adjust the example if needed.

| Entity | Icon | Meaning |
| --- | --- | --- |
| `binary_sensor.driveway_person_detected` | `mdi:walk` | Camera classified a detection as human/person |
| `binary_sensor.driveway_vehicle_detected` | `mdi:car` | Camera classified a detection as a vehicle |
| `binary_sensor.driveway_motion_detected` | `mdi:motion-sensor` | Motion alarm, including classified motion |
| `binary_sensor.driveway_camera_connection` | Connectivity device class | Most recent device-information poll succeeded |
| `binary_sensor.driveway_event_stream_connection` | Connectivity device class | A valid stream event/heartbeat was received on the current connection |
| `camera.driveway_snapshot` | `mdi:cctv` | Authenticated JPEG from the substream, with main-stream fallback |
| `sensor.driveway_model` / `sensor.driveway_firmware` | Camera / chip | Device identity and firmware |
| `sensor.driveway_last_event` | Bell | Last non-heartbeat alarm type and classified targets |
| `event.driveway_camera_event` | Camera | Every accepted non-heartbeat alarm, including unknown vendor types |
| `sensor.driveway_parameter_inventory` | List | Number of readable parameter/capability values, with endpoint status attributes |

Detection entities are created **only when discovered**. The table describes the available entity types; a camera will not necessarily get every detector. Newly discovered motion, person, vehicle, line-crossing, intrusion and region sensors are enabled by default. Tampering, video-loss, storage-fault and alarm-input sensors remain optional diagnostics, created disabled by default when supported. Existing entity IDs and user enable/disable choices are preserved.

## Automatic feature discovery

At setup and during polling, the integration reads system, event, per-channel and smart capability responses and probes known feature configuration/capability endpoints. It tries both `/ISAPI/Intelligent/channels/...` and `/ISAPI/Smart/...` paths for line crossing, intrusion and region events, remembering the path that actually works. The checks are GET requests only.

Each detector has three discovery outcomes:

| Outcome | Evidence |
| --- | --- |
| `supported` | A positive capability flag, advertised event/target type, readable feature configuration/capability document, or an actual matching event |
| `unsupported` | An explicit negative capability declaration, with no positive evidence |
| `unknown` | No positive/negative declaration; missing paths, permissions failures, timeouts, and incomplete replies do not prove a feature is absent |

A feature's **supported** status is separate from **enabled** configuration and from its current detection ON/OFF state. For example, a readable line-crossing configuration with `enabled=false` still creates a supported line-crossing detector and reports `feature_enabled: false`. The integration never enables the camera rule automatically. An omitted enable field is reported as unknown (`null`), not disabled.

The parameter-inventory sensor has a `features` attribute containing each outcome, configured enable state and discovery evidence. Download diagnostics for the feature report plus the individual API paths and their probe results. Detector entities expose `feature_support`, `feature_enabled`, and `discovery_evidence` attributes.

New capability or event evidence adds entities without an HA restart. Even if a capability response says false or omits a detector, a matching real event confirms it. Missing/unsupported endpoint caches are rechecked once an hour, and immediately after integration reload. Permission errors and transient failures are retried at each settings poll. If a detector loses its evidence temporarily, its existing entity becomes unavailable instead of falsely reporting OFF. Unknown vendor event types still reach the camera event entity.

On upgrade from 0.1.0, registry entries for formerly pre-created, unsupported/unknown detectors may remain unavailable. HA retains those historical entries and user enable/disable choices; you may remove obsolete ones from the entity registry. A previously disabled entry stays disabled until you enable it. No firmware compatibility list is used.

The event entity uses `event_type: camera_event` and attributes `camera_event_type`, `camera_event_state`, `targets`, `channel`, and `rule`. This preserves unknown vendor alarm types for automations even before a dedicated sensor mapping is added. It does not export full raw XML or image data.

Paste [the dashboard example](../examples/dashboard.yaml) into a manual dashboard card. It uses HA's built-in tiles and icons; no custom cards or icon files are needed.

## Detection semantics

- Person/vehicle states represent the camera's **recent detection events**, not a reliable count or continuous presence measurement.
- Detection activates immediately on matching active notifications. No human/vehicle classification is inferred from generic motion.
- Set Configure → **Sensor off debounce (seconds)** to keep sensors HIGH for X seconds after their last trigger ends. The default is 0 for compatibility. A new active notification cancels that source's pending LOW transition. Repeated inactive messages do not extend the delay. Independent rules are aggregated, so the sensor cannot clear while another source is active or still debouncing.
- Different event types and rule IDs are tracked separately. A line-crossing OFF cannot erase an ongoing motion/person detection from another source.
- The separate **Missing end-event timeout** defaults to 10 seconds: if an inactive notification is missing, the timeout infers the end, then the off debounce applies. Set the timeout to 0 to require an explicit end notification. Faults (storage error/full, video loss, alarm input) do not use that fallback; their inactive notifications still use the off debounce. Connection diagnostics and unavailable states are immediate.
- If the stream disconnects, detection/event entities become **unavailable** and cached active alarms are discarded. The integration reconnects with backoff from 2 to 60 seconds. Initial connectivity is established by a valid XML event or heartbeat, not just HTTP 200.
- `observed_in_stream: false` means that detector has not actually appeared in the stream during this integration run; support may instead have been established by an API response. An OFF state alone does not prove that detection is enabled. Camera enable/filter settings are separate from event states.
- Other channels are ignored. Inactive `videoloss` keepalives do not replace the last useful alarm. Missing event state is not interpreted as OFF.

## Camera parameters

The integration polls a bounded list of known read-only ISAPI endpoints every **120 seconds**, independently of immediate push detections. Areas include device status/uptime, time, capabilities, streaming codec/resolution/FPS configuration, image/night-mode settings, audio, motion/tamper settings, smart events, recording, storage, IO and network capabilities.

Every readable, non-sensitive XML scalar and capability attribute becomes an optional diagnostic sensor, created **disabled by default**. On the device page, expand disabled entities, select the desired parameter, and enable it. Parameters are string-valued direct API reports; camera-specific units or scales are not guessed. For example, a firmware's `maxFrameRate` may be encoded in hundredths of a frame per second.

For a complete readable inventory, use the integration entry menu → **Download diagnostics**. This includes endpoint status and the current sanitized parameter dictionary even when parameter entities are disabled. Configure → Create optional diagnostic parameter entities controls future registration; disabling it unloads parameter entities but does not delete existing registry records.

This cannot promise every private/vendor parameter. It covers the endpoints in `const.py`, not undisclosed firmware APIs, web-UI-only settings, or encrypted/privileged values. Credentials, known network identifiers, serial numbers, and sensitive XML subtrees are excluded from parameter entities and exports. Values longer than HA's 255-character state limit are marked, not stored as full sensor states. Responses are capped at 1 MiB per XML document, 3,000 values per endpoint, and 32 nested levels. These bounds can omit extreme responses.

404/405/501 and explicit ISAPI `notSupport` replies mark that endpoint path unavailable until the hourly rediscovery or reload. They do not, by themselves, declare the whole feature unsupported. Other errors are retried at the next poll and are reported as errors rather than invented sensor readings. A failed optional endpoint makes its old parameter entities unavailable; it does not take the whole device offline. The required device identity read determines camera connectivity. Credential rejection starts HA's normal reauthentication flow.

Use the integration entry menu → **Reconfigure** to change the IP, HTTP port, HTTPS options, username or password. The same serial number and channel are required, preserving entity identities after an IP change. Add additional cameras through Add integration.

## Snapshots and video

The I51HD returned **503 Device Busy** for `/ISAPI/Streaming/channels/101/picture` and a valid JPEG for `/ISAPI/Streaming/channels/102/picture`. The integration therefore prefers the lighter substream and falls back to the main stream if needed. Snapshots are fetched on demand, never included in diagnostic files.

The included camera entity provides **snapshots**, not RTSP live video or audio. Keep an existing ONVIF/Generic Camera/Frigate camera entity for live video, and combine it with these detection tiles if desired. Siren/light/PTZ/configuration writes and firmware updates are outside this read-only version.
