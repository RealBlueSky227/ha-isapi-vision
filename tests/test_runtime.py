"""Coordinator behavior with HA helper doubles, not a full HA startup test."""

import asyncio
import importlib
import sys
import types
import unittest
from unittest.mock import Mock, patch

from loader import api, protocol


class CoordinatorDouble:
    @classmethod
    def __class_getitem__(cls, key):
        return cls

    def __init__(self, hass, logger, **kwargs):
        self.hass = hass
        self.data = None
        self.last_update_success = True
        self.update_interval = kwargs["update_interval"]
        self.async_update_listeners = Mock()


class AuthFailed(Exception):
    pass


class UpdateFailed(Exception):
    pass


def module(name, **attributes):
    result = types.ModuleType(name)
    result.__dict__.update(attributes)
    return result


timer_cancel = Mock()
helpers = {
    "homeassistant": module("homeassistant"),
    "homeassistant.config_entries": module("homeassistant.config_entries", ConfigEntry=object),
    "homeassistant.core": module("homeassistant.core", HomeAssistant=object, callback=lambda func: func),
    "homeassistant.exceptions": module("homeassistant.exceptions", ConfigEntryAuthFailed=AuthFailed),
    "homeassistant.helpers": module("homeassistant.helpers"),
    "homeassistant.helpers.event": module(
        "homeassistant.helpers.event", async_track_time_interval=lambda *args: timer_cancel
    ),
    "homeassistant.helpers.update_coordinator": module(
        "homeassistant.helpers.update_coordinator", DataUpdateCoordinator=CoordinatorDouble, UpdateFailed=UpdateFailed
    ),
}
with patch.dict(sys.modules, helpers):
    runtime = importlib.import_module("isapi_vision_test.coordinator")


class EntryDouble:
    options = {}
    unique_id = "TEST123_1"

    def __init__(self):
        self.reauths = 0

    def async_create_background_task(self, hass, coro, name):
        return asyncio.create_task(coro, name=name)

    def async_start_reauth(self, hass):
        self.reauths += 1


class ClientDouble:
    channel = 1

    def __init__(self):
        self.release = asyncio.Event()
        self.entered = asyncio.Event()
        self.calls = 0
        self.disconnect_once = False
        self.auth_failure = False

    async def inventory(self):
        return api.Inventory({"serialNumber": "TEST123"}, {}, {})

    async def events(self, connected):
        self.calls += 1
        if self.auth_failure:
            raise api.CameraAuthError("test rejection")
        connected()
        yield protocol.CameraEvent("vmd", "active", "1", frozenset({"person"}), "")
        if self.disconnect_once and self.calls == 1:
            raise api.CameraError("test disconnect")
        self.entered.set()
        await self.release.wait()


class RuntimeTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        timer_cancel.reset_mock()
        self.entry = EntryDouble()
        self.client = ClientDouble()
        self.coordinator = runtime.IsapiVisionCoordinator(object(), self.entry, self.client)

    async def asyncTearDown(self):
        await self.coordinator.stop()

    async def test_poll_checks_identity_without_interfering_with_stream(self):
        self.coordinator.stream_connected = True
        result = await self.coordinator._async_update_data()
        self.assertEqual(result.device["serialNumber"], "TEST123")
        self.assertTrue(self.coordinator.stream_connected)
        self.entry.unique_id = "DIFFERENT_1"
        with self.assertRaises(UpdateFailed):
            await self.coordinator._async_update_data()

    async def test_start_stop_cleans_timer_task_and_alarms(self):
        self.coordinator.start()
        await asyncio.wait_for(self.client.entered.wait(), 1)
        self.assertTrue(self.coordinator.alarms.is_on("person"))
        self.assertTrue(self.coordinator.stream_connected)
        task = self.coordinator._stream_task
        await self.coordinator.stop()
        self.assertTrue(task.done())
        self.assertFalse(self.coordinator.stream_connected)
        self.assertFalse(self.coordinator.alarms.is_on("person"))
        timer_cancel.assert_called_once()

    async def test_disconnect_clears_alarms_and_reconnects(self):
        self.client.disconnect_once = True
        delays = []
        original_sleep = asyncio.sleep

        async def quick_retry(delay):
            self.assertFalse(self.coordinator.stream_connected)
            self.assertFalse(self.coordinator.alarms.is_on("person"))
            delays.append(delay)
            await original_sleep(0)

        with patch.object(runtime.asyncio, "sleep", quick_retry):
            self.coordinator.start()
            await asyncio.wait_for(self.client.entered.wait(), 1)
        self.assertEqual(delays, [2])
        self.assertEqual(self.client.calls, 2)
        self.assertTrue(self.coordinator.stream_connected)
        self.assertTrue(self.coordinator.alarms.is_on("person"))

    async def test_auth_failure_starts_reauth_and_stops_retrying(self):
        self.client.auth_failure = True
        self.coordinator.start()
        await asyncio.wait_for(self.coordinator._stream_task, 1)
        self.assertEqual(self.entry.reauths, 1)
        self.assertEqual(self.client.calls, 1)
        self.assertEqual(self.coordinator.stream_error, "invalid_auth")
        self.assertFalse(self.coordinator.stream_connected)

    async def test_event_listeners_receive_one_event_and_can_unsubscribe(self):
        received = []
        remove = self.coordinator.async_add_event_listener(received.append)
        self.coordinator.start()
        await asyncio.wait_for(self.client.entered.wait(), 1)
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0].targets, {"person"})
        self.assertEqual(self.coordinator.observed_event_types, {"vmd"})
        remove()
        self.assertEqual(self.coordinator._event_listeners, [])

    async def test_tick_expires_detection_and_notifies_entities(self):
        self.coordinator.alarms.apply(protocol.CameraEvent("vmd", "active", "1", frozenset({"person"}), ""), 0)
        with patch.object(runtime.time, "monotonic", return_value=11):
            self.coordinator._expire(None)
        self.assertFalse(self.coordinator.alarms.is_on("person"))
        self.coordinator.async_update_listeners.assert_called_once()
