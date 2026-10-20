"""Shared device identity."""

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import IsapiVisionCoordinator


class IsapiVisionEntity(CoordinatorEntity[IsapiVisionCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: IsapiVisionCoordinator, key: str) -> None:
        super().__init__(coordinator)
        device = coordinator.data.device
        self._attr_unique_id = f"{coordinator.entry.unique_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device["serialNumber"])},
            manufacturer=device.get("manufacturer"),
            model=device.get("model"),
            name=coordinator.entry.title,
            sw_version=device.get("firmwareVersion"),
            configuration_url=str(coordinator.client.base_url),
        )
