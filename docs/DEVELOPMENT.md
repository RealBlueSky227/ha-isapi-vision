# Development and read-only troubleshooting tools

Standalone tests need Python 3.12+ and the development dependencies:

```sh
python -m pip install -r requirements-dev.txt
python -m ruff check .
python -m ruff format --check .
python -m unittest discover -s tests -v
python tools/check_release.py
python tools/package.py
```

Real HA tests use Linux/Python 3.14 and pinned `pytest-homeassistant-custom-component==0.13.373`, which installs HA 2026.10.2. Install the native packages shown in `.github/workflows/ci.yml`, then:

```sh
python -m pip install -r requirements-test-ha.txt
python -m pytest tests_ha -q --cov=custom_components.isapi_vision.config_flow --cov-report=term-missing --cov-fail-under=100
```

The local HTTPS fixture generates its key/certificate at runtime in a temporary directory. No test private key is committed. Network-enabled tests contact loopback only; CI never needs real camera access or credentials.

On a machine with camera access, the optional probe can read the inventory, try a snapshot and observe the persistent event stream:

```sh
python tools/probe.py --host 192.0.2.10 --username camera-reader --events 60
python tools/probe.py --host 192.0.2.10 --username camera-reader --https --port 443 --events 60
```

Both prompt for the password without echoing it. Add `--insecure` only to intentionally skip HTTPS certificate identity validation after verifying the device separately. Otherwise the certificate must be trusted and match the host. The probe saves a sanitized, ignored `camera-inventory.json`; inspect it before sharing. Neither the probe nor the integration modifies camera configuration.

For individual known read-only paths, use `tools/inspect_paths.py --host 192.0.2.10 --path /ISAPI/System/capabilities`. Tools are in the source checkout, not automatically copied into HA's `/config/tools` or installed by HACS. On Docker, run them from the source checkout with the required dependencies, or explicitly mount that checkout into a disposable Python environment.

`tools/package.py` builds a manual-install `isapi_vision.zip` and a curated source ZIP. Its source allowlist excludes `.git`, local inventories, HA `.storage`, caches and old archives. HACS installs the integration subdirectory from the chosen release tag; the manual component ZIP has `manifest.json` at its root and must be extracted into `/config/custom_components/isapi_vision`.
