# Quality and release readiness

The integration follows a [Bronze self-audit](custom_components/isapi_vision/quality_scale.yaml). It has **not** been awarded an HA Core quality tier. The manifest deliberately makes no `quality_scale: bronze` claim.

| Area | Implementation / evidence |
| --- | --- |
| Configuration | UI flow with device identity test before configuration and setup; serial/channel uniqueness; reauth/reconfigure; no saved password defaults. |
| Data fetching | Immediate persistent event push; separate bounded 120-second settings poll and hourly missing-endpoint rechecks. |
| Runtime/lifecycle | Typed config-entry runtime data; cancelled stream/ticker; removed event subscriptions and coordinator listeners; tests for unload/reload. |
| Entities | Serial/channel-derived unique IDs; named entities; optional diagnostics disabled by default; supported-only detector creation. |
| Dependencies | Empty runtime requirements: stdlib plus HA-provided libraries. No separate MQTT service or extra Python install at runtime. |
| Safety | Read-only GET APIs, no redirects, Digest authentication, default certificate validation, bounded DTD-rejecting XML, sanitized diagnostics. |
| Documentation | Installation, upgrades, entities, automations, limitations, removal, security, contributing and compatibility reporting. |
| Branding | Original camera artwork; local 256/512 PNGs in the integration `brand/` directory. |
| Tests | Real HA 2026.10.2 config-flow/platform tests with 100% config-flow line coverage; standalone transport/protocol/discovery/debounce/migration tests. |
| Public release | Official HACS Action and Hassfest without disabled checks; curated packaging; first release is explicitly a GitHub prerelease. |

There are no integration-specific services/actions, device triggers or device conditions. Use standard sensor-state/event automations and native camera actions. Camera-write controls are outside this release.

[CI results](https://github.com/RealBlueSky227/ha-isapi-vision/actions/workflows/ci.yml) · [Validation and remaining physical checks](VALIDATION.md) · [HACS catalog preparation](docs/HACS_SUBMISSION.md)
