"""Independent cameras, reload/restart-equivalent cleanup and stable registered identities."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry
from yarl import URL

from custom_components.isapi_vision.api import Inventory
from custom_components.isapi_vision.const import DOMAIN
from custom_components.isapi_vision.discovery import FeatureInfo
from custom_components.isapi_vision.protocol import CameraEvent

from .test_config_flow import DATA


async def test_multiple_cameras_and_reload_keep_registered_ids(hass):
    def make_camera(serial, target):
        async def events(connected):
            connected()
            yield CameraEvent("vmd", "active", "1", frozenset({target}), "1")
            await asyncio.Event().wait()

        return SimpleNamespace(
            channel=1,
            base_url=URL("http://192.0.2.10"),
            events=events,
            inventory=AsyncMock(
                return_value=Inventory(
                    {"serialNumber": serial},
                    {},
                    {},
                    {key: FeatureInfo("supported", True) for key in ("person", "vehicle", "motion")},
                )
            ),
            snapshot=AsyncMock(return_value=b"\xff\xd8test\xff\xd9"),
        )

    entries = [
        MockConfigEntry(domain=DOMAIN, unique_id=f"{serial}_1", title=title, data=DATA | {"host": host})
        for serial, title, host in (("TEST-A", "Driveway", "192.0.2.10"), ("TEST-B", "Garage", "192.0.2.11"))
    ]
    clients = {"192.0.2.10": make_camera("TEST-A", "person"), "192.0.2.11": make_camera("TEST-B", "vehicle")}
    for entry in entries:
        entry.add_to_hass(hass)
    with patch("custom_components.isapi_vision.make_client", side_effect=lambda hass, data: clients[data["host"]]):
        for entry in entries:
            assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert hass.states.get("binary_sensor.driveway_person_detected").state == "on"
        assert hass.states.get("binary_sensor.driveway_vehicle_detected").state == "off"
        assert hass.states.get("binary_sensor.garage_person_detected").state == "off"
        assert hass.states.get("binary_sensor.garage_vehicle_detected").state == "on"
        registry = er.async_get(hass)
        before = {
            row.entity_id: (row.id, row.unique_id, row.device_id)
            for row in er.async_entries_for_config_entry(registry, entries[0].entry_id)
        }
        previous = entries[0].runtime_data
        assert await hass.config_entries.async_reload(entries[0].entry_id)
        await hass.async_block_till_done()
        assert previous._stream_task is None and previous._cancel_ticker is None
        assert entries[0].runtime_data is not previous
        assert hass.states.get("binary_sensor.driveway_person_detected").state == "on"
        assert hass.states.get("binary_sensor.garage_vehicle_detected").state == "on"
        after = {
            row.entity_id: (row.id, row.unique_id, row.device_id)
            for row in er.async_entries_for_config_entry(registry, entries[0].entry_id)
        }
        assert before == after
        for entry in entries:
            assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
