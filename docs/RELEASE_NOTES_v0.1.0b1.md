# ISAPI Vision v0.1.0 Beta 1

First public beta of ISAPI Vision, an MIT-licensed, local, read-only, push-based Home Assistant camera integration using ISAPI.

## Included

- Persistent ISAPI alert-stream events with discovered person, vehicle, motion and supported smart-event sensors; native event entity and dashboard icons.
- Capability/configuration/event evidence instead of firmware guesses; supported, unsupported and unknown remain distinct.
- Post-end off debounce, separate missing end-event timeout, independent source aggregation, reconnect handling and unavailable states.
- Optional settings diagnostics, sanitized exports and authenticated JPEG snapshots with substream/main-stream fallback.
- Multiple camera entries, identity-preserving upgrades, reauth/reconfigure, exact password preservation, HTTPS and explicit certificate errors.
- Existing project branding, HACS metadata, issue forms and official HACS/Hassfest validation.

## Compatibility and limits

Primary development camera: **ANNKE FCD600**, reported **I51HD**, firmware **V5.8.10**. Device/settings/capability reads, stream keepalives and snapshots were verified previously. Authenticated HTTPS device-information access was confirmed in a deployed HA container with certificate verification disabled for the camera's mismatched certificate. No new physical camera tests are claimed for release preparation. Deliberate physical person/vehicle activations, timing and disconnect acceptance remain pending; regression tests use synthetic events and local HTTP/TLS fixtures. Other ANNKE/Hikvision-style ISAPI models are experimental.

Read-only, snapshot-only: no PTZ, siren, light, alarm-output writes, camera configuration changes, firmware updates, RTSP live video or audio. Camera events are recent detections, not continuous occupancy. Discovery covers known endpoints, not every proprietary parameter. This is not official vendor software or an awarded HA Core quality tier.

## Install the beta

1. In HACS → ⋮ → Custom repositories, add **https://github.com/RealBlueSky227/ha-isapi-vision**, category **Integration**.
2. Open ISAPI Vision → Download (or ⋮ → Redownload), enable **Show beta versions**, and select **v0.1.0b1**.
3. Restart Home Assistant, then add **ISAPI Vision** under Settings → Devices & services.

Requires HA 2025.7+; release CI targets current stable 2026.10.2. Local logos require HA 2026.3+. This works as a HACS custom repository; official catalog acceptance is separate and has not been requested automatically.

Manual installation: extract the attached `isapi_vision.zip` directly into `/config/custom_components/isapi_vision`, then restart HA. `manifest.json` must sit directly in that folder.

The domain remains `isapi_vision`, config-entry version stays 1, and serial/channel-derived entity identities are unchanged. Existing ISAPI Vision installations do not need re-adding. The public version series restarts at 0.1.0b1; select the beta explicitly when replacing a private 0.4.0 build. Legacy `annke_isapi` installations need the separately documented offline migration; HACS does not execute it automatically.

## Feedback

Testers with other cameras are welcome. Report bugs or model/firmware compatibility at **https://github.com/RealBlueSky227/ha-isapi-vision/issues/new/choose**. Distinguish discovered capabilities from actual observed detections. Inspect diagnostics first; never post credentials, private addresses, serial numbers, raw XML or camera images. Announcements and the official HACS submission remain subject to maintainer review.
