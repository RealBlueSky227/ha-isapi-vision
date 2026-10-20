# Contributing to ISAPI Vision

This beta welcomes reproducible bug reports and camera compatibility evidence. Use the GitHub templates and include integration/HA versions, model, firmware, the affected feature and observed behavior. Positive capability evidence and explicit negative declarations are both useful; a missing endpoint alone is not proof that a feature is unsupported.

Never post passwords, tokens, real IP addresses/hostnames, camera serial numbers, snapshots, config-entry exports, raw XML or unreviewed diagnostic files. Use `192.0.2.10` / `2001:db8::10` for examples and synthetic credentials for tests. Security reports should use [the private reporting process](SECURITY.md).

Changes should preserve entity unique IDs, config entries, device identifiers and immediate push updates. Keep camera access read-only unless a separate feature proposal explicitly scopes and tests writes. Do not add unconditional entities or firmware/model heuristics for feature support. Optional diagnostics should stay disabled by default unless there is a clear reason to change that default.

Run the documented lint, standalone tests, packaging checks and real HA tests before proposing a PR; see [development](docs/DEVELOPMENT.md). Add regression tests for a demonstrated bug using minimal sanitized XML, not captures containing private values. Explain physical hardware evidence separately from mocked tests. Include model/firmware only when actually verified.

The existing MIT license applies to contributions. Small focused PRs are preferred. HACS catalog submission and public announcements require maintainer review; do not open duplicate submissions or post announcements on behalf of the project.
