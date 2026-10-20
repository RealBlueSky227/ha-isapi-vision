"""ISAPI Vision integration."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .client import make_client
from .coordinator import IsapiVisionCoordinator

PLATFORMS = [Platform.BINARY_SENSOR, Platform.SENSOR, Platform.CAMERA, Platform.EVENT]
type IsapiVisionConfigEntry = ConfigEntry[IsapiVisionCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: IsapiVisionConfigEntry) -> bool:
    coordinator = IsapiVisionCoordinator(hass, entry, make_client(hass, entry.data))
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_reload))
    entry.async_on_unload(coordinator.stop)
    coordinator.start()
    return True


async def async_unload_entry(hass: HomeAssistant, entry: IsapiVisionConfigEntry) -> bool:
    if await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        await entry.runtime_data.stop()
        return True
    return False


async def _reload(hass: HomeAssistant, entry: IsapiVisionConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
