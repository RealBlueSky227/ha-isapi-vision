# Public beta announcement drafts

These drafts are prepared for maintainer review. They have not been posted automatically. Release notes use the same scope and compatibility limits.

## Home Assistant Community Forum

Title: **ISAPI Vision public beta: local ISAPI camera events, discovery and snapshots**

ISAPI Vision is an open-source, local, push-based Home Assistant integration for cameras exposing Hikvision-style ISAPI. The first public beta provides discovered person, vehicle, motion and supported smart-event sensors; configurable off debounce; native camera events; optional parameter diagnostics; and authenticated JPEG snapshots. It talks directly to the camera without MQTT or a cloud service.

Development hardware is ANNKE FCD600 (reported model I51HD), firmware V5.8.10. Device reads, capabilities, keepalives, snapshots and HTTPS device-information access have been verified. Deliberate physical person/vehicle activation and timing remain acceptance checks; automated tests use synthetic events. Other ANNKE/Hikvision-compatible models are experimental, and smart events appear only with positive capability/configuration/event evidence.

Install through HACS → Custom repositories: add https://github.com/RealBlueSky227/ha-isapi-vision as **Integration**, open ISAPI Vision, enable **Show beta versions** in Download/Redownload and select **v0.1.0b1**, then restart HA and add the integration. This is a custom HACS repository, not an approved catalog listing.

The beta is read-only and snapshot-only: no PTZ/siren/light/configuration writes or RTSP live video. Camera firmware controls detection accuracy. Existing ISAPI Vision entity identities are preserved.

Testers with other ANNKE/Hikvision-style ISAPI cameras are welcome. Please report model, firmware, discovered features and actual observed events through https://github.com/RealBlueSky227/ha-isapi-vision/issues/new/choose. Review diagnostics before posting; omit credentials, private addresses, serial numbers and images.

Release: https://github.com/RealBlueSky227/ha-isapi-vision/releases/tag/v0.1.0b1

## Reddit r/homeassistant

Title: **ISAPI Vision beta — local ISAPI camera sensors and snapshots, no MQTT**

I’m sharing ISAPI Vision, an MIT-licensed, local push-based camera integration for Home Assistant. It discovers supported person/vehicle/motion and smart events from ISAPI replies, exposes native sensors/events, offers post-end debounce and optional diagnostics, and provides JPEG snapshots.

Primary development hardware is ANNKE FCD600 / I51HD, firmware V5.8.10. Other Hikvision-style ISAPI models are experimental; real person/vehicle trigger and timing acceptance tests remain pending, with synthetic-event regression coverage in CI. No cloud/MQTT requirement, live RTSP stream or camera-write controls.

Try it as a HACS custom repository (**Integration**): https://github.com/RealBlueSky227/ha-isapi-vision. Enable beta versions in Download/Redownload, select **v0.1.0b1**, restart HA, then add ISAPI Vision. It is not in the official HACS catalog yet.

Looking for testers with other compatible cameras. Model/firmware and sanitized compatibility reports: https://github.com/RealBlueSky227/ha-isapi-vision/issues/new/choose. Please keep credentials, addresses, serial numbers and camera images private.

## GitHub prerelease notes

See [the reviewed release note source](RELEASE_NOTES_v0.1.0b1.md). The published release adds links to the validated commit/run and available installation assets.
