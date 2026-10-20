"""Poll settings and independently supervise the push event stream."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from contextlib import suppress
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import CameraAuthError, CameraError, EndpointError, Inventory, IsapiVisionClient
from .const import DEFAULT_OPTIONS, DOMAIN
from .discovery import FeatureInfo
from .protocol import AlarmState, CameraEvent

_LOGGER = logging.getLogger(__name__)


class IsapiVisionCoordinator(DataUpdateCoordinator[Inventory]):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client: IsapiVisionClient) -> None:
        options = DEFAULT_OPTIONS | dict(entry.options)
        super().__init__(
            hass, _LOGGER, name=DOMAIN, config_entry=entry, update_interval=timedelta(seconds=options["scan_interval"])
        )
        self.entry = entry
        self.client = client
        self.alarms = AlarmState(client.channel, options["alarm_hold"], options["debounce_seconds"])
        self.stream_connected = False
        self.stream_error: str | None = None
        self._stream_task: asyncio.Task | None = None
        self._cancel_ticker = None
        self.event_sequence = 0
        self.last_camera_event: CameraEvent | None = None
        self.observed_event_types: set[str] = set()
        self._event_listeners: list[Callable[[CameraEvent], None]] = []

    @property
    def features(self) -> dict[str, FeatureInfo]:
        features = dict(self.data.features) if self.data else {}
        for key in self.alarms.seen:
            features[key] = features.get(key, FeatureInfo()).observed()
        return features

    async def _async_update_data(self) -> Inventory:
        try:
            inventory = await self.client.inventory()
        except CameraAuthError as err:
            raise ConfigEntryAuthFailed("Check camera credentials and account permissions") from err
        except CameraError as err:
            raise UpdateFailed("Cannot read camera information") from err
        expected = f"{inventory.device['serialNumber']}_{self.client.channel}"
        if self.entry.unique_id != expected:
            raise UpdateFailed("A different camera is now responding at this address")
        return inventory

    @callback
    def start(self) -> None:
        self._cancel_ticker = async_track_time_interval(self.hass, self._expire, timedelta(seconds=1))
        self._stream_task = self.entry.async_create_background_task(self.hass, self._listen(), "ISAPI Vision alerts")

    @callback
    def async_add_event_listener(self, listener: Callable[[CameraEvent], None]) -> Callable[[], None]:
        self._event_listeners.append(listener)
        return lambda: self._event_listeners.remove(listener)

    async def stop(self) -> None:
        if self._cancel_ticker:
            self._cancel_ticker()
            self._cancel_ticker = None
        if self._stream_task:
            self._stream_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._stream_task
            self._stream_task = None
        self.stream_connected = False
        self.alarms.clear()

    @callback
    def _expire(self, _now) -> None:
        if self.alarms.expire(time.monotonic()):
            self.async_update_listeners()

    @callback
    def _connected(self) -> None:
        self.stream_connected = True
        self.stream_error = None
        self.async_update_listeners()

    async def _listen(self) -> None:
        delay = 2
        while True:
            try:
                async for event in self.client.events(self._connected):
                    delay = 2
                    if self.alarms.apply(event, time.monotonic()):
                        self.event_sequence += 1
                        self.last_camera_event = event
                        if len(self.observed_event_types) < 128:
                            self.observed_event_types.add(event.event_type)
                        for listener in tuple(self._event_listeners):
                            listener(event)
                        self.async_update_listeners()
            except CameraAuthError:
                self.stream_error = "invalid_auth"
                self.entry.async_start_reauth(self.hass)
                return
            except EndpointError as err:
                self.stream_error = "permission_denied" if err.status == 403 else f"http_{err.status}"
            except CameraError:
                self.stream_error = "stream_unavailable"
                _LOGGER.debug("ISAPI Vision event stream unavailable; reconnecting in %s seconds", delay)
            finally:
                self.stream_connected = False
                self.alarms.clear()
                self.async_update_listeners()
            await asyncio.sleep(delay)
            delay = min(delay * 2, 60)
