"""Verify registration/availability with HA entity doubles, not a full HA instance."""

import importlib
import sys
import types
import unittest
from unittest.mock import Mock, patch

from loader import api, protocol
from test_runtime import ClientDouble, EntryDouble, helpers, module, runtime

discovery = importlib.import_module("isapi_vision_test.discovery")


class EntityDouble:
    @classmethod
    def __class_getitem__(cls, key):
        return cls

    def __init__(self, coordinator):
        self.coordinator = coordinator


entity_helpers = helpers | {
    "isapi_vision_test.coordinator": runtime,
    "homeassistant.components": module("homeassistant.components"),
    "homeassistant.components.binary_sensor": module(
        "homeassistant.components.binary_sensor", BinarySensorEntity=type("BinarySensorDouble", (), {})
    ),
    "homeassistant.const": module("homeassistant.const", EntityCategory=types.SimpleNamespace(DIAGNOSTIC="diagnostic")),
    "homeassistant.helpers.device_registry": module("homeassistant.helpers.device_registry", DeviceInfo=dict),
    "homeassistant.helpers.update_coordinator": module(
        "homeassistant.helpers.update_coordinator", CoordinatorEntity=EntityDouble
    ),
}
with patch.dict(sys.modules, entity_helpers):
    binary_sensor = importlib.import_module("isapi_vision_test.binary_sensor")


class DiscoveryEntityTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.entry = EntryDouble()
        self.entry.title = "Driveway"
        self.entry.async_on_unload = Mock()
        self.client = ClientDouble()
        self.client.base_url = "http://camera"
        self.coordinator = runtime.IsapiVisionCoordinator(object(), self.entry, self.client)
        self.coordinator.data = api.Inventory(
            {"serialNumber": "TEST123"},
            {},
            {},
            {
                "person": discovery.FeatureInfo("supported", True),
                "line_crossing": discovery.FeatureInfo("unknown"),
                "intrusion": discovery.FeatureInfo("unsupported"),
            },
        )
        self.entry.runtime_data = self.coordinator
        self.listeners = []

        def add_listener(listener):
            self.listeners.append(listener)
            return lambda: self.listeners.remove(listener)

        self.coordinator.async_add_listener = add_listener
        self.added = []
        await binary_sensor.async_setup_entry(None, self.entry, self.added.extend)

    def detectors(self):
        return {entity.key: entity for entity in self.added if isinstance(entity, binary_sensor.IsapiVisionDetection)}

    def notify(self):
        for listener in tuple(self.listeners):
            listener()

    async def test_only_confirmed_detectors_created(self):
        self.assertEqual(set(self.detectors()), {"person"})
        self.assertEqual(len(self.added), 3)  # two health entities plus the discovered detector

    async def test_later_discovery_adds_entity_once_with_stable_id(self):
        self.coordinator.data.features["line_crossing"] = discovery.FeatureInfo("supported", False)
        self.notify()
        self.notify()
        self.assertEqual(set(self.detectors()), {"person", "line_crossing"})
        self.assertEqual(len(self.added), 4)
        entity = self.detectors()["line_crossing"]
        self.assertEqual(entity._attr_unique_id, "TEST123_1_line_crossing")
        self.assertTrue(entity._attr_entity_registry_enabled_default)
        self.assertIs(entity.extra_state_attributes["feature_enabled"], False)

    async def test_observed_event_discovers_feature_missing_from_capabilities(self):
        self.coordinator.alarms.apply(
            protocol.CameraEvent("lineDetection".lower(), "active", "1", frozenset({"person"}), ""), 0
        )
        self.notify()
        self.assertIn("line_crossing", self.detectors())
        self.assertTrue(self.detectors()["line_crossing"].is_on)
        self.assertIn("event_stream", self.detectors()["line_crossing"].extra_state_attributes["discovery_evidence"])

    async def test_old_entity_becomes_unavailable_instead_of_false_off(self):
        entity = self.detectors()["person"]
        self.coordinator.stream_connected = True
        self.assertTrue(entity.available)
        self.coordinator.data.features["person"] = discovery.FeatureInfo("unknown")
        self.notify()
        self.assertFalse(entity.available)

    async def test_registration_listener_removed_on_unload(self):
        remove = self.entry.async_on_unload.call_args.args[0]
        remove()
        self.assertEqual(self.listeners, [])
