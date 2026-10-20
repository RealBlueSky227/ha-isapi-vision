"""Create clients with HA's shared HTTP session; no configuration lives here."""

from collections.abc import Mapping
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import IsapiVisionClient


def make_client(hass: HomeAssistant, data: Mapping[str, Any]) -> IsapiVisionClient:
    return IsapiVisionClient(
        async_get_clientsession(hass, verify_ssl=data.get("verify_ssl", True)),
        data["host"],
        data["username"],
        data["password"],
        data.get("port", 80),
        data.get("use_ssl", False),
        data.get("channel", 1),
    )
