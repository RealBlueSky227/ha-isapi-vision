"""Offline migration must preserve identities and credentials, or leave files unchanged."""

import importlib.util
import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    "vision_migration", Path(__file__).resolve().parents[1] / "tools/migrate_domain.py"
)
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)


def documents():
    return {
        "core.config_entries": {
            "version": 1,
            "minor_version": 5,
            "data": {
                "entries": [
                    {
                        "entry_id": "camera-entry",
                        "domain": "annke_isapi",
                        "unique_id": "SERIAL_1",
                        "title": "Driveway",
                        "data": {"password": " synthetic Ω secret ", "username": "camera-account"},
                        "options": {"debounce_seconds": 9},
                    },
                    {"entry_id": "other-entry", "domain": "unrelated", "unique_id": "other", "data": {}},
                ]
            },
        },
        "core.entity_registry": {
            "version": 1,
            "data": {
                "entities": [
                    {
                        "entity_id": "binary_sensor.custom_person",
                        "platform": "annke_isapi",
                        "config_entry_id": "camera-entry",
                        "unique_id": "SERIAL_1_person",
                        "device_id": "camera-device",
                        "disabled_by": "user",
                    },
                    {
                        "entity_id": "sensor.other",
                        "platform": "unrelated",
                        "config_entry_id": "other-entry",
                        "unique_id": "other",
                    },
                ]
            },
        },
        "core.device_registry": {
            "version": 1,
            "data": {
                "devices": [
                    {
                        "id": "camera-device",
                        "identifiers": [["annke_isapi", "SERIAL"], ["other-platform", "extra"]],
                        "config_entries": ["camera-entry", "shared-entry"],
                        "name_by_user": "Driveway camera",
                    },
                ]
            },
        },
    }


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.config = Path(self.temp.name)
        self.storage = self.config / ".storage"
        self.storage.mkdir()
        self.original = {}
        for name, document in documents().items():
            content = json.dumps(document).encode()
            (self.storage / name).write_bytes(content)
            self.original[name] = content

    def assert_original(self):
        for name, content in self.original.items():
            self.assertEqual((self.storage / name).read_bytes(), content)

    def test_only_namespaces_change_and_input_is_immutable(self):
        source = documents()
        untouched = deepcopy(source)
        updated, counts = migration.transform(source)
        expected = deepcopy(source)
        expected["core.config_entries"]["data"]["entries"][0]["domain"] = "isapi_vision"
        expected["core.entity_registry"]["data"]["entities"][0]["platform"] = "isapi_vision"
        expected["core.device_registry"]["data"]["devices"][0]["identifiers"][0][0] = "isapi_vision"
        self.assertEqual(updated, expected)
        self.assertEqual(source, untouched)
        self.assertEqual(counts, {"entries": 1, "entities": 1, "device_identifiers": 1})

    def test_dry_run_writes_nothing(self):
        counts, backup = migration.migrate(self.config)
        self.assertEqual(counts["entries"], 1)
        self.assertIsNone(backup)
        self.assertFalse((self.config / "backups").exists())
        self.assert_original()

    def test_apply_requires_stopped_acknowledgement(self):
        with self.assertRaises(ValueError):
            migration.migrate(self.config, apply=True)
        self.assert_original()

    def test_apply_exact_backups_and_idempotent(self):
        _, backup = migration.migrate(self.config, apply=True, ha_stopped=True)
        for name, content in self.original.items():
            self.assertEqual((backup / name).read_bytes(), content)
        counts, second_backup = migration.migrate(self.config, apply=True, ha_stopped=True)
        self.assertEqual(counts, {"entries": 0, "entities": 0, "device_identifiers": 0})
        self.assertIsNone(second_backup)

    def test_failed_write_rolls_back_all_replaced_files(self):
        real_replace = migration.os.replace
        calls = 0

        def fail_once(source, target):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("Simulated write failure")
            return real_replace(source, target)

        with patch.object(migration.os, "replace", side_effect=fail_once), self.assertRaises(OSError):
            migration.migrate(self.config, apply=True, ha_stopped=True)
        self.assert_original()
        self.assertFalse(list(self.storage.glob(".isapi-vision-*")))

    def test_changed_registry_aborts_before_writes(self):
        real_stage = migration._stage

        def concurrent_change(path, content):
            result = real_stage(path, content)
            (self.storage / "core.config_entries").write_bytes(b"changed externally")
            return result

        with patch.object(migration, "_stage", side_effect=concurrent_change), self.assertRaises(ValueError):
            migration.migrate(self.config, apply=True, ha_stopped=True)
        self.assertEqual((self.storage / "core.entity_registry").read_bytes(), self.original["core.entity_registry"])

    def test_unknown_storage_version_rejected(self):
        source = documents()
        source["core.entity_registry"]["version"] = 99
        with self.assertRaises(ValueError):
            migration.transform(source)

    def test_duplicate_entry_rejected(self):
        source = documents()
        duplicate = deepcopy(source["core.config_entries"]["data"]["entries"][0])
        duplicate.update(domain="isapi_vision", entry_id="existing-new-entry")
        source["core.config_entries"]["data"]["entries"].append(duplicate)
        with self.assertRaises(ValueError):
            migration.transform(source)

    def test_duplicate_entity_rejected(self):
        source = documents()
        duplicate = deepcopy(source["core.entity_registry"]["data"]["entities"][0])
        duplicate.update(platform="isapi_vision", entity_id="binary_sensor.other_name")
        source["core.entity_registry"]["data"]["entities"].append(duplicate)
        with self.assertRaises(ValueError):
            migration.transform(source)

    def test_duplicate_device_rejected(self):
        source = documents()
        source["core.device_registry"]["data"]["devices"].append(
            {"id": "duplicate", "identifiers": [["isapi_vision", "SERIAL"]], "config_entries": ["other-entry"]}
        )
        with self.assertRaises(ValueError):
            migration.transform(source)

    def test_empty_registries_are_supported(self):
        source = {name: {"version": 1, "data": {key: []}} for name, key in migration.TABLES.items()}
        updated, counts = migration.transform(source)
        self.assertEqual(updated, source)
        self.assertEqual(counts["entries"], 0)

    def test_default_title_is_renamed(self):
        source = documents()
        source["core.config_entries"]["data"]["entries"][0]["title"] = "ANNKE ISAPI"
        updated, _ = migration.transform(source)
        self.assertEqual(updated["core.config_entries"]["data"]["entries"][0]["title"], "ISAPI Vision")

    def test_missing_registry_is_safe(self):
        (self.storage / "core.entity_registry").unlink()
        counts, _ = migration.migrate(self.config, apply=True, ha_stopped=True)
        self.assertEqual(counts["entries"], 1)
        self.assertEqual(counts["entities"], 0)

    def test_current_ha_v3_device_registry_and_multiple_channels(self):
        source = documents()
        registry = source["core.device_registry"]
        registry["version"] = 3
        device = registry["data"]["devices"][0]
        device.pop("config_entries")
        device["config_entry_id"] = "camera-entry"
        another = deepcopy(device)
        another.update(id="another-channel-device", config_entry_id="another-channel-entry")
        registry["data"]["devices"].append(another)
        entry = deepcopy(source["core.config_entries"]["data"]["entries"][0])
        entry.update(entry_id="another-channel-entry", unique_id="SERIAL_2")
        source["core.config_entries"]["data"]["entries"].append(entry)
        updated, counts = migration.transform(source)
        self.assertEqual(counts["device_identifiers"], 2)
        for item in updated["core.device_registry"]["data"]["devices"]:
            self.assertEqual(item["identifiers"][0][0], "isapi_vision")

    def test_deleted_entities_and_child_devices_preserved(self):
        source = documents()
        entity_data = source["core.entity_registry"]["data"]
        deleted = deepcopy(entity_data["entities"][0])
        deleted.update(entity_id="binary_sensor.old_motion", unique_id="SERIAL_1_motion")
        entity_data["deleted_entities"] = [deleted]
        registry = source["core.device_registry"]
        registry["version"] = 3
        child = {
            "id": "child",
            "config_entry_id": "camera-entry",
            "parent_device_id": "camera-device",
            "identifiers": [["annke_isapi", "SERIAL-child"]],
        }
        registry["data"]["child_devices"] = [child]
        updated, _ = migration.transform(source)
        self.assertEqual(updated["core.entity_registry"]["data"]["deleted_entities"][0]["platform"], "isapi_vision")
        self.assertEqual(
            updated["core.device_registry"]["data"]["child_devices"][0]["identifiers"][0][0], "isapi_vision"
        )
