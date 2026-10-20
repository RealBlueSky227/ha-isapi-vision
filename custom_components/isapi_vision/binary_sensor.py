"""Detection icons and availability diagnostics."""

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import callback

from .const import DETECTIONS, PERSISTENT_ALARMS
from .discovery import FeatureInfo
from .entity import IsapiVisionEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    coordinator = entry.runtime_data
    async_add_entities([IsapiVisionConnection(coordinator, "camera"), IsapiVisionConnection(coordinator, "events")])
    added = set()

    @callback
    def add_discovered_detections() -> None:
        supported = {
            key for key, info in coordinator.features.items() if info.support == "supported" and key in DETECTIONS
        }
        new = supported - added
        if new:
            added.update(new)
            async_add_entities([IsapiVisionDetection(coordinator, key) for key in sorted(new)])

    add_discovered_detections()
    entry.async_on_unload(coordinator.async_add_listener(add_discovered_detections))


class IsapiVisionDetection(IsapiVisionEntity, BinarySensorEntity):
    def __init__(self, coordinator, key) -> None:
        super().__init__(coordinator, key)
        self.key = key
        name, icon, device_class, enabled = DETECTIONS[key]
        self._attr_name = name
        self._attr_icon = icon
        self._attr_device_class = device_class
        self._attr_entity_registry_enabled_default = enabled

    @property
    def available(self) -> bool:
        feature = self.coordinator.features.get(self.key, FeatureInfo())
        return self.coordinator.stream_connected and feature.support == "supported"

    @property
    def is_on(self) -> bool:
        return self.coordinator.alarms.is_on(self.key)

    @property
    def extra_state_attributes(self) -> dict:
        feature = self.coordinator.features.get(self.key, FeatureInfo())
        return {
            "feature_support": feature.support,
            "feature_enabled": feature.enabled,
            "discovery_evidence": feature.evidence,
            "observed_in_stream": self.key in self.coordinator.alarms.seen,
            "missing_end_timeout_seconds": None
            if self.key in PERSISTENT_ALARMS or not self.coordinator.alarms.hold
            else self.coordinator.alarms.hold,
            "debounce_seconds": self.coordinator.alarms.debounce,
            "state_source": "camera_event_stream",
        }


class IsapiVisionConnection(IsapiVisionEntity, BinarySensorEntity):
    _attr_device_class = "connectivity"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, key) -> None:
        super().__init__(coordinator, f"{key}_connection")
        self.key = key
        self._attr_name = "Camera connection" if key == "camera" else "Event stream connection"

    @property
    def available(self) -> bool:
        return True

    @property
    def is_on(self) -> bool:
        if self.key == "camera":
            return self.coordinator.last_update_success
        return self.coordinator.stream_connected

    @property
    def extra_state_attributes(self) -> dict:
        return {"error": self.coordinator.stream_error} if self.key == "events" else {}
