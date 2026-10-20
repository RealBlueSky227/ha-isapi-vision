"""Load actual HA platforms and verify runtime data and unload cleanup."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry
from yarl import URL

from custom_components.isapi_vision.api import Inventory
from custom_components.isapi_vision.const import DOMAIN
from custom_components.isapi_vision.discovery import FeatureInfo
from custom_components.isapi_vision.protocol import CameraEvent
from tools.migrate_domain import transform

from .test_config_flow import DATA


@pytest.mark.parametrize("migrated", [False, True])
async def test_setup_real_platforms_then_unload(hass, migrated):
    inventory = Inventory(
        {"serialNumber": "TEST-SERIAL", "model": "Test camera", "firmwareVersion": "test"},
        {},
        {},
        {"person": FeatureInfo("supported", True), "motion": FeatureInfo("supported", True)},
    )

    async def events(connected):
        connected()
        yield CameraEvent("vmd", "active", "1", frozenset({"person"}), "1")
        await asyncio.Event().wait()

    client = SimpleNamespace(
        channel=1,
        base_url=URL("http://192.0.2.10"),
        inventory=AsyncMock(return_value=inventory),
        events=events,
        snapshot=AsyncMock(return_value=b"\xff\xd8test\xff\xd9"),
    )
    entry = MockConfigEntry(domain=DOMAIN, unique_id="TEST-SERIAL_1", data=DATA, title="Driveway")
    entry.add_to_hass(hass)
    person_id = "binary_sensor.driveway_person_detected"
    existing_device = None
    if migrated:
        converted, _ = transform(
            {
                "core.config_entries": {
                    "version": 1,
                    "data": {
                        "entries": [
                            {
                                "domain": "annke_isapi",
                                "entry_id": entry.entry_id,
                                "unique_id": entry.unique_id,
                                "data": DATA,
                            }
                        ]
                    },
                },
                "core.entity_registry": {
                    "version": 1,
                    "data": {
                        "entities": [
                            {
                                "platform": "annke_isapi",
                                "config_entry_id": entry.entry_id,
                                "unique_id": "TEST-SERIAL_1_person",
                                "entity_id": "binary_sensor.existing_driveway_person",
                            }
                        ]
                    },
                },
                "core.device_registry": {
                    "version": 3,
                    "data": {
                        "devices": [
                            {"config_entry_id": entry.entry_id, "identifiers": [["annke_isapi", "TEST-SERIAL"]]}
                        ]
                    },
                },
            }
        )
        row = converted["core.entity_registry"]["data"]["entities"][0]
        device_row = converted["core.device_registry"]["data"]["devices"][0]
        existing_device = dr.async_get(hass).async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={tuple(item) for item in device_row["identifiers"]},
            name="Driveway",
        )
        registry_entry = er.async_get(hass).async_get_or_create(
            "binary_sensor",
            row["platform"],
            row["unique_id"],
            suggested_object_id="existing_driveway_person",
            config_entry=entry,
            device_id=existing_device.id,
        )
        er.async_get(hass).async_update_entity(registry_entry.entity_id, name="Saved person label")
        person_id = registry_entry.entity_id
    with patch("custom_components.isapi_vision.make_client", return_value=client):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    coordinator = entry.runtime_data
    assert coordinator.stream_connected
    person = hass.states.get(person_id)
    assert person is not None
    assert person.state == "on"
    if migrated:
        registered = er.async_get(hass).async_get(person_id)
        assert registered.device_id == existing_device.id
        assert registered.name == "Saved person label"
        assert hass.states.get("binary_sensor.driveway_person_detected") is None
    assert hass.states.get("camera.driveway_snapshot") is not None
    assert hass.states.get("event.driveway_camera_event") is not None
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert coordinator._stream_task is None
    assert coordinator._cancel_ticker is None
    assert not coordinator.stream_connected
