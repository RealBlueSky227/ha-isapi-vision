# Changelog

## 0.1.0b2 — active-defense controls

- Discover audible and flashing alarm capabilities/configuration with GET requests only.
- Add momentary Home Assistant buttons for discovered outputs; no output is activated during setup or polling.
- Use the selected camera `audioID` for the documented audible-alarm test command instead of assuming a model-specific ID.
- Try channelled and unchannelled white-light test paths only after positive strobe discovery, without changing alarm schedules or saved camera configuration.
- Report control discovery evidence in diagnostics and surface rejected commands as Home Assistant errors.

## 0.1.0b1 — public beta

First public ISAPI Vision beta. The public version series begins at 0.1.0b1; earlier private development builds used other version numbers.

- Preserve native, persistent ISAPI push events, automatic feature discovery, person/vehicle/motion and supported smart-event sensors.
- Preserve post-end debounce, missing-end handling, reconnect/unavailable behavior, event entities, optional parameter diagnostics and authenticated JPEG snapshots.
- Preserve the `isapi_vision` domain, config-entry version, unique IDs and device identifier namespace. Keep the separate offline migration for legacy `annke_isapi` installations.
- Add HACS custom-repository installation, official HACS validation with no ignored checks, release packaging, issue forms, contribution guidance and beta announcements.
- Keep the existing camera artwork and prepare GitHub/HA assets from it.
- Report certificate verification failures explicitly and explain HTTPS trust/hostname matching. Use a number box for camera channel selection.
- Add regression checks for HTTPS with HA's shared sessions, multiple cameras and lifecycle reloads.

No camera-write controls, live RTSP streaming or new firmware-based feature assumptions are introduced.
