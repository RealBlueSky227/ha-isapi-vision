#!/usr/bin/env bash
# Install into an existing Docker Compose HA service, migrating the former domain.
set -euo pipefail

compose_dir="$(realpath "${1:-$HOME/docker}")"
config_dir="$(realpath "${2:-$compose_dir/homeassistant}")"
package_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$compose_dir"
test -f "$package_dir/custom_components/isapi_vision/manifest.json"
docker compose config --services | grep -Fxq homeassistant
mapfile -t containers < <(docker compose ps --all --quiet homeassistant)
if [ "${#containers[@]}" -ne 1 ]; then
  echo 'Expected one existing homeassistant service container. Check the Compose project.' >&2
  exit 1
fi
mounted_config="$(docker inspect --format '{{range .Mounts}}{{if eq .Destination "/config"}}{{.Source}}{{end}}{{end}}' "${containers[0]}")"
if [ "$mounted_config" != "$config_dir" ]; then
  echo 'The service /config bind mount does not match the specified configuration directory.' >&2
  exit 1
fi
docker compose stop homeassistant
if [ "$(docker inspect --format '{{.State.Running}}' "${containers[0]}")" != false ]; then
  echo 'Home Assistant is still running. Migration was not attempted.' >&2
  exit 1
fi
docker compose run --rm --no-deps --entrypoint python \
  -v "$package_dir:/isapi-vision:ro" homeassistant \
  /isapi-vision/tools/migrate_domain.py --config /config --apply --ha-stopped
sudo mkdir -p "$config_dir/backups" "$config_dir/custom_components"
backup="$(sudo mktemp -d "$config_dir/backups/isapi-vision-code-XXXXXXXX")"
for domain in annke_isapi isapi_vision; do
  if [ -d "$config_dir/custom_components/$domain" ]; then
    sudo mv -- "$config_dir/custom_components/$domain" "$backup/"
  fi
done
sudo cp -a -- "$package_dir/custom_components/isapi_vision" "$config_dir/custom_components/"
echo "Previous integration code: $backup"
docker compose up -d --no-deps homeassistant
docker compose logs --tail=60 homeassistant
