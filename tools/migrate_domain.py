"""One-time, offline registry migration to ISAPI Vision. Home Assistant must be stopped."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import tempfile
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

OLD_DOMAIN = "annke_isapi"
NEW_DOMAIN = "isapi_vision"
TABLES = {
    "core.config_entries": "entries",
    "core.entity_registry": "entities",
    "core.device_registry": "devices",
}


def transform(documents: dict) -> tuple[dict, dict]:
    """Change only domain associations, preserving IDs, credentials, options and names."""
    result = deepcopy(documents)
    for name, document in result.items():
        if (
            name not in TABLES
            or not isinstance(document, dict)
            or document.get("version") not in ((1, 2, 3) if name == "core.device_registry" else (1,))
            or not isinstance(document.get("data"), dict)
            or not isinstance(document["data"].get(TABLES[name]), list)
            or not all(isinstance(row, dict) for row in document["data"][TABLES[name]])
        ):
            raise ValueError("Unsupported registry format; no changes made")
    entries = result.get("core.config_entries", {}).get("data", {}).get("entries", [])
    old_entries = [entry for entry in entries if entry.get("domain") == OLD_DOMAIN]
    ids = {entry.get("entry_id") for entry in old_entries}
    if None in ids or len(ids) != len(old_entries):
        raise ValueError("Invalid legacy entry IDs; no changes made")
    existing_unique_ids = {entry.get("unique_id") for entry in entries if entry.get("domain") == NEW_DOMAIN}
    for entry in old_entries:
        if entry.get("unique_id") is not None and entry["unique_id"] in existing_unique_ids:
            raise ValueError("Duplicate camera entry in destination domain; no changes made")
        existing_unique_ids.add(entry.get("unique_id"))
        entry["domain"] = NEW_DOMAIN
        if entry.get("title") == "ANNKE ISAPI":
            entry["title"] = "ISAPI Vision"
    entity_data = result.get("core.entity_registry", {}).get("data", {})
    entities = entity_data.get("entities", []) + entity_data.get("deleted_entities", [])
    entity_count = 0
    seen_entities = set()
    for entity in entities:
        if entity.get("config_entry_id") in ids and entity.get("platform") == OLD_DOMAIN:
            entity["platform"] = NEW_DOMAIN
            entity_count += 1
        if entity.get("platform") == NEW_DOMAIN:
            key = (entity.get("entity_id", "").split(".")[0], entity.get("unique_id"))
            if key in seen_entities:
                raise ValueError("Duplicate destination entity; no changes made")
            seen_entities.add(key)
    device_document = result.get("core.device_registry", {})
    device_data = device_document.get("data", {})
    devices = (
        device_data.get("devices", []) + device_data.get("child_devices", []) + device_data.get("deleted_devices", [])
    )
    device_count = 0
    seen_identifiers = set()
    for device in devices:
        identifiers = device.get("identifiers", [])
        if not isinstance(identifiers, list) or not all(
            isinstance(item, list) and len(item) == 2 and all(isinstance(value, str) for value in item)
            for item in identifiers
        ):
            raise ValueError("Unsupported device identifiers; no changes made")
        owners = set(device.get("config_entries", [])) | {device.get("config_entry_id")}
        if ids.intersection(owners):
            for item in identifiers:
                if item[0] == OLD_DOMAIN:
                    item[0] = NEW_DOMAIN
                    device_count += 1
            if device.get("domain") == OLD_DOMAIN:
                device["domain"] = NEW_DOMAIN
        for item in identifiers:
            if item[0] == NEW_DOMAIN:
                # HA registry v3 namespaces identifiers per config entry; v1/v2 are global.
                key = (device.get("config_entry_id") if device_document.get("version") == 3 else None, *item)
                if key in seen_identifiers:
                    raise ValueError("Duplicate destination device; no changes made")
                seen_identifiers.add(key)
    return result, {"entries": len(ids), "entities": entity_count, "device_identifiers": device_count}


def _stage(path: Path, content: bytes) -> Path:
    """Prepare an atomic replacement with the original permissions and ownership."""
    handle, name = tempfile.mkstemp(prefix=".isapi-vision-", dir=path.parent)
    staged = Path(name)
    try:
        with os.fdopen(handle, "wb") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        shutil.copystat(path, staged)
        if hasattr(os, "chown"):
            info = path.stat()
            os.chown(staged, info.st_uid, info.st_gid)
    except BaseException:
        staged.unlink(missing_ok=True)
        raise
    return staged


def migrate(config: Path, *, apply: bool = False, ha_stopped: bool = False) -> tuple[dict, Path | None]:
    """Validate everything first; retain protected backups and roll back write failures."""
    if apply and not ha_stopped:
        raise ValueError("Stop Home Assistant and pass --ha-stopped before applying")
    config = config.resolve(strict=True)
    storage = config / ".storage"
    if not storage.is_dir() or storage.is_symlink():
        raise ValueError("Expected a real HA .storage directory")
    raw = {}
    documents = {}
    for name in TABLES:
        path = storage / name
        if path.is_symlink():
            raise ValueError("Registry symlinks are not supported")
        if path.exists():
            raw[name] = path.read_bytes()
            documents[name] = json.loads(raw[name])
    if "core.config_entries" not in documents:
        raise ValueError("HA config-entry registry is missing")
    updated, counts = transform(documents)
    changed = [name for name in documents if updated[name] != documents[name]]
    if not apply or not changed:
        return counts, None
    backups = config / "backups"
    if backups.is_symlink():
        raise ValueError("Backup directory symlinks are not supported")
    backups.mkdir(exist_ok=True)
    backup = Path(tempfile.mkdtemp(prefix=f"isapi-vision-migration-{datetime.now(UTC):%Y%m%d-%H%M%S}-", dir=backups))
    backup.chmod(0o700)
    # Back up all present registries, including credentials, with owner-only access.
    for name, content in raw.items():
        with os.fdopen(os.open(backup / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
    staged = {}
    replaced = []
    try:
        for name in changed:
            staged[name] = _stage(
                storage / name, (json.dumps(updated[name], ensure_ascii=False, indent=2) + "\n").encode()
            )
        if any((storage / name).read_bytes() != content for name, content in raw.items()):
            raise ValueError("Registry changed during migration; HA must remain stopped")
        for name in changed:
            os.replace(staged[name], storage / name)
            replaced.append(name)
    except BaseException:
        for name in reversed(replaced):
            os.replace(_stage(storage / name, raw[name]), storage / name)
        raise
    finally:
        for path in staged.values():
            path.unlink(missing_ok=True)
    return counts, backup


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path, help="HA configuration directory")
    parser.add_argument("--apply", action="store_true", help="Apply changes; default is a read-only dry run")
    parser.add_argument("--ha-stopped", action="store_true", help="Confirm the HA process is fully stopped")
    args = parser.parse_args()
    try:
        counts, backup = migrate(args.config, apply=args.apply, ha_stopped=args.ha_stopped)
    except (OSError, ValueError, TypeError, KeyError):
        # Never print registry values, exception text or credentials.
        parser.exit(1, "Migration failed. Keep HA stopped; inspect the format and protected backups before retrying.\n")
    print(("Applied" if args.apply else "Dry run") + ": " + json.dumps(counts))
    if backup:
        print(f"Protected registry backups: {backup}")


if __name__ == "__main__":
    main()
