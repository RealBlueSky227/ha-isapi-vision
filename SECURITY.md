# Credential and data handling

The integration is local and read-only. It authenticates using HTTP Digest, sends GET requests only, disables redirects, and never embeds credentials in URLs. Use a camera account with only the permissions needed to read settings, snapshots and events. Prefer HTTPS with certificate validation when the camera supports it. HTTP Digest authenticates requests; HTTP by itself does not encrypt images or settings traffic.

Passwords are accepted through HA's password selector and stored in the normal config entry. They are not schema defaults, including after errors, reconfiguration or reauthentication. Leaving the optional password blank preserves the saved password. Passwords are passed verbatim; whitespace and Unicode are not stripped. This integration does not encrypt HA's config entry storage independently: protect your HA configuration directory and backups.

Logs report generic error categories and never intentionally include passwords, request headers, raw camera XML or config-entry data. Diagnostic exports contain only selected identity information, feature evidence and sanitized settings. Sensitive XML fields/subtrees are excluded, and exact credentials or the configured hostname echoed in exported field values, attributes or identifiers are redacted. No sanitization system can identify every proprietary secret field; inspect diagnostics before sharing them.

XML is parsed using the standard library with a custom TreeBuilder that rejects every DTD in the parser callback (including UTF-16 encodings). External/custom entity declarations cannot be processed. Input size, nesting and element count are bounded. HTTP bodies and stream buffers are bounded as well. The integration adds no third-party runtime requirements beyond libraries provided by HA.

Never commit camera passwords, HA config entries, backups, real camera inventories or tokens. The repository ignores local inventories, archives, environments and coverage output. Test credentials are synthetic and never access a physical camera. CI uses mocked cameras and does not require device credentials.

Report suspected credential exposure with [GitHub private vulnerability reporting](https://github.com/RealBlueSky227/ha-isapi-vision/security/advisories/new). Do not put sensitive details in public issues. If that form is unavailable, open a public issue requesting a private reporting channel without including the vulnerability or private data. Rotate an exposed camera credential through the camera UI, then use HA's Reconfigure flow to update it.
