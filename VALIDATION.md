# Beta validation and compatibility evidence

## Hardware evidence

Development hardware is **ANNKE FCD600**, reporting model **I51HD**, firmware **V5.8.10**. Prior read-only checks verified device identity, a sanitized inventory of 573 values, motion classification configuration (`human,vehicle`), surveillance-center linkage, valid channel-1 stream keepalives and a JPEG from substream 102. Main-stream 101 returned 503 Device Busy, motivating the existing substream preference/fallback.

Motion/person/vehicle capability support was confirmed; tamper support was present but disabled. Storage-error support was advertised. Storage-full and video-loss alarm support were explicitly false. Line crossing, intrusion, region entrance/exit and alarm input remained unknown on the checked firmware/API paths. These are discovery observations, not a model-wide compatibility table. No camera configuration writes were made.

A deployed HA-container test subsequently confirmed authenticated HTTPS device-information access. The camera's certificate did not match its IP address, and access worked with certificate verification disabled. This does not establish a trusted certificate chain or hostname match.

No new physical camera tests are claimed during public-release preparation. Deliberate physical person/vehicle triggers, exact end-event timing, disconnection/recovery and other camera models remain acceptance tests. Classification behavior is covered with synthetic XML fixtures. Do not infer physical event confirmation from an HTTP 200 or a heartbeat.

## Automated release gates

The [Integration checks workflow](https://github.com/RealBlueSky227/ha-isapi-vision/actions/workflows/ci.yml) runs:

- Official HACS Action with **no ignored checks**, and HA Hassfest.
- Ruff lint/format, Bash deployment syntax, metadata/privacy contract and verified source/component ZIP packaging.
- Standalone protocol/transport tests: Digest authentication, malformed/oversized/DTD XML, split stream frames, target classification, source aggregation, inactive/watchdog/debounce timing, redaction, disconnects and reconnects.
- Real HA **2026.10.2** tests using Python 3.14, including config flow, credential preservation, reauth/reconfigure/options, platform setup/unload, migrated identities, reload and independent cameras. CI enforces **100% line coverage of config_flow.py**.
- A local self-signed HTTPS fixture verifies the actual HA shared-session path: verification rejects the certificate; explicit verification disablement permits the TLS request. It never contacts a physical camera.
- Offline migration tests validate preserved data/IDs/options, read-only previews, exact backups, duplicate rejection, registry v1/v3 layouts, concurrency detection and rollback.

All CI camera identities, credentials and XML are synthetic. The release is created only from a commit whose required workflow jobs passed. Exact totals and the successful run are included in release notes; this document does not claim 100% overall integration coverage.

## Public distribution audit

Only audited source and original project artwork enter the public repository. Private development history is retained privately because earlier documentation and author metadata contained deployment details. Runtime inventories, configuration storage, logs, tokens and old local release archives are excluded. The public history uses the maintainer's GitHub no-reply identity. Pattern-based checks reduce accidental exposure but do not replace manual review of diagnostic exports.

## Installation acceptance

After installing the beta, confirm snapshot and stream connectivity; trigger real person and vehicle events; verify debounce after the last end event; disconnect/reconnect the camera; restart HA; confirm existing entity IDs and automations still work. Additional model reports should distinguish successful capability reads, actual events and unsupported/unknown features.
