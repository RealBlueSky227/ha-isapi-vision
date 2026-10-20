# Changelog

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
