"""Authenticated snapshots with substream preference and main-stream fallback."""

from homeassistant.components.camera import Camera

from .api import CameraError
from .entity import IsapiVisionEntity

PARALLEL_UPDATES = 1


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    async_add_entities([IsapiVisionCamera(entry.runtime_data)])


class IsapiVisionCamera(IsapiVisionEntity, Camera):
    _attr_name = "Snapshot"
    _attr_icon = "mdi:cctv"

    def __init__(self, coordinator) -> None:
        Camera.__init__(self)
        IsapiVisionEntity.__init__(self, coordinator, "snapshot")

    async def async_camera_image(self, width=None, height=None) -> bytes | None:
        try:
            return await self.coordinator.client.snapshot()
        except CameraError:
            return None
