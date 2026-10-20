"""Expose every non-heartbeat camera alarm, including unmapped vendor event types."""

from homeassistant.components.event import EventEntity
from homeassistant.core import callback

from .entity import IsapiVisionEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    async_add_entities([IsapiVisionEvent(entry.runtime_data)])


class IsapiVisionEvent(IsapiVisionEntity, EventEntity):
    _attr_name = "Camera event"
    _attr_icon = "mdi:cctv"
    _attr_event_types = ["camera_event"]

    def __init__(self, coordinator) -> None:
        EventEntity.__init__(self)
        IsapiVisionEntity.__init__(self, coordinator, "camera_event")

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self.coordinator.async_add_event_listener(self._camera_event))

    @property
    def available(self) -> bool:
        return self.coordinator.stream_connected

    @callback
    def _camera_event(self, event) -> None:
        self._trigger_event(
            "camera_event",
            {
                "camera_event_type": event.event_type,
                "camera_event_state": event.state,
                "targets": sorted(event.targets),
                "channel": event.channel,
                "rule": event.rule,
            },
        )
        self.async_write_ha_state()
