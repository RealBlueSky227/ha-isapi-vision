# Install or upgrade ISAPI Vision

Requires Home Assistant 2025.7 or newer. Local branding displays in HA 2026.3 and newer. Enter camera credentials through the HA integration form; never put passwords into deployment commands.

HACS installation is described in [README.md](README.md). Existing `isapi_vision` entries require no domain migration. The procedure below is for manual Docker installation and legacy upgrades.

## Docker Compose with SCP

These examples assume an existing Compose service named `homeassistant`, Compose files in `~/docker`, and a bind mount from `~/docker/homeassistant` to `/config`. Replace `HA_ACCOUNT@HA_HOST` with the server login. The deployment script checks that the selected container mounts the expected configuration directory before stopping it.

From Windows PowerShell, copy the component and deployment tools (no Git history or local camera inventory):

```powershell
Set-Location C:\path\to\ha-isapi-vision
ssh HA_ACCOUNT@HA_HOST "mkdir -p ~/docker/isapi-vision"
scp -r custom_components tools HA_ACCOUNT@HA_HOST:~/docker/isapi-vision/
ssh -t HA_ACCOUNT@HA_HOST 'bash ~/docker/isapi-vision/tools/deploy_docker.sh'
```

For a different server layout, pass the absolute Compose directory and HA configuration directory:

```sh
bash ~/docker/isapi-vision/tools/deploy_docker.sh /srv/docker /srv/homeassistant
```

The script stops only the HA service, verifies it has stopped, runs the offline domain migration using the HA image's Python, backs up existing integration folders, installs `custom_components/isapi_vision`, and starts HA. It does not require Python on the host. If a step fails after HA stops, it stays stopped so the reported problem can be resolved before restarting. Existing camera credentials, options, config-entry IDs, device IDs, entity IDs and dashboard references are preserved by the migration. Other Compose services continue running.

For a new installation, open **Settings → Devices & services → Add integration → ISAPI Vision**. Enter the camera host, channel and credentials. For an upgrade, the existing entry appears under the new integration without adding the camera again. Refresh the browser if a cached name or icon remains.

## Domain migration from versions 0.1–0.3

The former domain was `annke_isapi`; the private development rename and the public beta use `isapi_vision`. Copying only the new folder and restarting is insufficient for existing installations. The Docker script above performs the required one-time migration and removes the old component folder from the active installation by moving it into a backup.

The migration tool changes only the matching config-entry domain, entity platform and device identifier namespace. Camera-derived unique IDs and entity IDs remain unchanged. It validates the registry layout and rejects duplicate destination entries/entities/devices. All existing registry files are backed up byte-for-byte under `backups/isapi-vision-migration-*` before writes. Those backups contain saved credentials: directories are owner-only and files are mode 0600 on Linux. Keep them private.

For non-Docker installations, stop HA completely, copy the new component folder, and run this with the environment's Python before starting HA:

```sh
# Read-only preview; prints counts, never credentials.
python tools/migrate_domain.py --config /path/to/ha-config
# Only after HA is fully stopped:
python tools/migrate_domain.py --config /path/to/ha-config --apply --ha-stopped
```

Move the old `custom_components/annke_isapi` folder out of `custom_components` after a successful migration. Do not edit or migrate `.storage` while HA is running. The tool is idempotent; later deployments find zero legacy entries and leave the registries unchanged. Atomic replacement protects each file, and write failures trigger rollback. A machine/power failure between file replacements may require restoring all registry backups together before restarting.

## Rollback

Keep HA stopped. Restore **all** files from the selected `backups/isapi-vision-migration-*` directory into `.storage`, preserving file permissions. Restore the matching old component folder from `backups/isapi-vision-code-*`, and move the new component folder out of `custom_components`. Start HA only after code and registries are on the same domain. Registry backups represent the pre-upgrade state; later HA configuration changes are not included.

## Git checkout alternative

```sh
git clone https://github.com/RealBlueSky227/ha-isapi-vision.git
bash ha-isapi-vision/tools/deploy_docker.sh
```

The public repository can be cloned without a token. Do not put camera credentials or GitHub tokens into clone/deployment commands.

After installation, verify snapshots, event-stream connectivity, physical person/vehicle detections and the selected debounce. Update legacy MQTT dashboard references before retiring a separate MQTT listener; native entity IDs are independent of MQTT discovery IDs.
