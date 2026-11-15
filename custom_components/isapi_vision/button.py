"""Capability-gated, momentary active-defense controls."""

from homeassistant.components.button import ButtonEntity
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError

from .api import CameraError
from .entity import IsapiVisionEntity

PARALLEL_UPDATES = 0

CONTROLS = {
    "audible_alarm": ("Sound audible alarm", "mdi:alarm-bell"),
    "flashing_alarm": ("Flash alarm light", "mdi:alarm-light"),
}


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    coordinator = entry.runtime_data
    added: set[str] = set()

    @callback
    def add_discovered_controls() -> None:
        new = set(coordinator.data.controls) - added
        if new:
            added.update(new)
            async_add_entities(IsapiVisionOutputButton(coordinator, key) for key in sorted(new))

    add_discovered_controls()
    entry.async_on_unload(coordinator.async_add_listener(add_discovered_controls))


class IsapiVisionOutputButton(IsapiVisionEntity, ButtonEntity):
    """Run one bounded camera output test when deliberately pressed."""

    def __init__(self, coordinator, key: str) -> None:
        super().__init__(coordinator, f"{key}_test")
        self.key = key
        self._attr_name, self._attr_icon = CONTROLS[key]

    @property
    def available(self) -> bool:
        return super().available and self.key in self.coordinator.data.controls

    async def async_press(self) -> None:
        try:
            await self.coordinator.client.activate_output(self.key)
        except CameraError as err:
            raise HomeAssistantError(f"Camera rejected the {self._attr_name.lower()} command") from err

    @property
    def extra_state_attributes(self) -> dict:
        control = self.coordinator.data.controls.get(self.key)
        return {"command_type": "momentary_test", "discovery_evidence": control.evidence if control else None}
