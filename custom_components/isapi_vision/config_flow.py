"""UI setup, credential repair, connection editing, and sensor behavior."""

from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import CameraAuthError, CameraCertificateError, CameraError
from .client import make_client
from .const import DEFAULT_OPTIONS, DOMAIN

_LOGGER = logging.getLogger(__name__)


def connection_schema(defaults: dict, new: bool) -> vol.Schema:
    """Passwords are never defaults, including after errors or during reauth."""
    password_key = vol.Required("password") if new else vol.Optional("password")
    return vol.Schema(
        {
            vol.Required("host", default=defaults.get("host", "")): str,
            vol.Required("username", default=defaults.get("username", "admin")): str,
            password_key: TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD)),
            vol.Required("port", default=defaults.get("port", 80)): vol.All(
                vol.Coerce(int), vol.Range(min=1, max=65535)
            ),
            vol.Required("use_ssl", default=defaults.get("use_ssl", False)): bool,
            vol.Required("verify_ssl", default=defaults.get("verify_ssl", True)): bool,
            vol.Required("channel", default=defaults.get("channel", 1)): vol.All(
                NumberSelector(NumberSelectorConfig(min=1, max=64, step=1, mode=NumberSelectorMode.BOX)),
                vol.Coerce(int),
            ),
        }
    )


def options_schema(values: dict) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required("alarm_hold", default=values["alarm_hold"]): vol.All(
                vol.Coerce(int), vol.Range(min=0, max=3600)
            ),
            vol.Required("debounce_seconds", default=values["debounce_seconds"]): vol.All(
                vol.Coerce(int), vol.Range(min=0, max=3600)
            ),
            vol.Required("parameter_entities", default=values["parameter_entities"]): bool,
        }
    )


class IsapiVisionConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        return await self._connection_step("user", user_input)

    async def async_step_reconfigure(self, user_input=None):
        return await self._connection_step("reconfigure", user_input, self._get_reconfigure_entry())

    async def async_step_reauth(self, entry_data):
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        return await self._connection_step("reauth_confirm", user_input, self._get_reauth_entry())

    async def _connection_step(self, step, user_input, entry=None):
        defaults = {key: value for key, value in entry.data.items() if key != "password"} if entry else {}
        errors = {}
        if user_input is not None:
            data = (dict(entry.data) if entry else {}) | user_input
            if entry and not user_input.get("password"):
                data["password"] = entry.data["password"]
            data["host"] = data["host"].strip().strip("[]")
            if not data["host"] or any(char in data["host"] for char in "/@?#"):
                errors["host"] = "invalid_host"
            elif not data.get("password"):
                errors["password"] = "password_required"
            else:
                try:
                    device = await make_client(self.hass, data).device_info()
                except CameraAuthError:
                    errors["base"] = "invalid_auth"
                except CameraCertificateError:
                    errors["base"] = "invalid_certificate"
                except CameraError:
                    errors["base"] = "cannot_connect"
                except ValueError:
                    errors["host"] = "invalid_host"
                except Exception:  # Third-party error strings can contain credentials.
                    _LOGGER.error("Unexpected error validating the camera connection")
                    errors["base"] = "unknown"
                else:
                    unique_id = f"{device['serialNumber']}_{data['channel']}"
                    if entry:
                        if unique_id != entry.unique_id:
                            errors["base"] = "wrong_device"
                        else:
                            return self.async_update_reload_and_abort(entry, data=data)
                    else:
                        await self.async_set_unique_id(unique_id)
                        self._abort_if_unique_id_configured()
                        return self.async_create_entry(title=device.get("deviceName") or "ISAPI Vision", data=data)
            defaults.update({key: value for key, value in user_input.items() if key != "password"})
        return self.async_show_form(step_id=step, data_schema=connection_schema(defaults, entry is None), errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return IsapiVisionOptionsFlow()


class IsapiVisionOptionsFlow(config_entries.OptionsFlow):
    async def async_step_init(self, user_input=None):
        values = DEFAULT_OPTIONS | dict(self.config_entry.options)
        errors = {}
        if user_input is not None:
            try:
                validated = options_schema(values)(user_input)
            except vol.Invalid:
                errors["base"] = "invalid_options"
            else:
                return self.async_create_entry(title="", data=dict(self.config_entry.options) | validated)
        return self.async_show_form(step_id="init", data_schema=options_schema(values), errors=errors)
