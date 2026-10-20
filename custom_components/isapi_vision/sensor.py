"""Camera event summary and optional scalar parameter entities."""

from homeassistant.components.sensor import SensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import callback

from .const import DEFAULT_OPTIONS
from .discovery import feature_report
from .entity import IsapiVisionEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        [
            IsapiVisionSummary(coordinator, "model", "Model", "mdi:cctv"),
            IsapiVisionSummary(coordinator, "firmwareVersion", "Firmware", "mdi:chip"),
            IsapiVisionSummary(coordinator, "last_event", "Last event", "mdi:bell-outline"),
            IsapiVisionSummary(coordinator, "inventory", "Parameter inventory", "mdi:list-box-outline"),
        ]
    )
    if not entry.options.get("parameter_entities", DEFAULT_OPTIONS["parameter_entities"]):
        return
    added = set()

    @callback
    def add_parameters() -> None:
        new = set(coordinator.data.parameters) - added
        if new:
            added.update(new)
            async_add_entities(IsapiVisionParameter(coordinator, key) for key in sorted(new))

    add_parameters()
    entry.async_on_unload(coordinator.async_add_listener(add_parameters))


class IsapiVisionSummary(IsapiVisionEntity, SensorEntity):
    def __init__(self, coordinator, key, name, icon) -> None:
        super().__init__(coordinator, key)
        self.key = key
        self._attr_name = name
        self._attr_icon = icon
        if key != "last_event":
            self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def available(self) -> bool:
        return self.coordinator.stream_connected if self.key == "last_event" else super().available

    @property
    def native_value(self):
        if self.key == "last_event":
            return self.coordinator.alarms.last_event
        if self.key == "inventory":
            return len(self.coordinator.data.parameters)
        return self.coordinator.data.device.get(self.key)

    @property
    def extra_state_attributes(self) -> dict:
        if self.key == "inventory":
            return {"endpoints": self.coordinator.data.endpoints, "features": feature_report(self.coordinator.features)}
        if self.key == "last_event":
            event = self.coordinator.last_camera_event
            return {
                "targets": self.coordinator.alarms.last_targets,
                "camera_event_state": event.state if event else None,
                "channel": event.channel if event else None,
                "rule": event.rule if event else None,
            }
        return {}


class IsapiVisionParameter(IsapiVisionEntity, SensorEntity):
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False
    _attr_icon = "mdi:tune"

    def __init__(self, coordinator, key) -> None:
        super().__init__(coordinator, f"parameter_{key}")
        self.key = key
        self._attr_name = key.replace("/", " · ")

    @property
    def available(self) -> bool:
        return super().available and self.key in self.coordinator.data.parameters

    @property
    def native_value(self):
        return self.coordinator.data.parameters.get(self.key)

    @property
    def extra_state_attributes(self) -> dict:
        return {"isapi_parameter": self.key}
