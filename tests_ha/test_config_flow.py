"""Exercise every config-flow path using HA's flow manager and real selectors."""

from unittest.mock import patch

import pytest
import voluptuous as vol
from homeassistant.config_entries import SOURCE_REAUTH, SOURCE_RECONFIGURE, SOURCE_USER
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.isapi_vision.api import CameraAuthError, CameraCertificateError, CameraError
from custom_components.isapi_vision.config_flow import IsapiVisionOptionsFlow
from custom_components.isapi_vision.const import DOMAIN

SECRET = "Example-Test-Password-Only!"
DATA = {
    "host": "192.0.2.10",
    "username": "camera-reader",
    "password": SECRET,
    "port": 80,
    "use_ssl": False,
    "verify_ssl": True,
    "channel": 1,
}


def assert_password_is_empty(result):
    key = next(key for key in result["data_schema"].schema if key.schema == "password")
    assert key.default is vol.UNDEFINED


async def user_form(hass):
    return await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})


async def test_user_success_and_duplicate(hass, camera_client, mock_setup):
    result = await user_form(hass)
    assert result["type"] is FlowResultType.FORM
    assert_password_is_empty(result)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], DATA)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == "TEST-SERIAL_1"
    assert result["title"] == "Driveway"
    assert result["data"] == DATA
    await hass.async_block_till_done()
    duplicate = await user_form(hass)
    duplicate = await hass.config_entries.flow.async_configure(duplicate["flow_id"], DATA)
    assert duplicate["type"] is FlowResultType.ABORT
    assert duplicate["reason"] == "already_configured"


@pytest.mark.parametrize(
    ("error", "field", "message"),
    [
        (CameraAuthError(SECRET), "base", "invalid_auth"),
        (CameraCertificateError(SECRET), "base", "invalid_certificate"),
        (CameraError(SECRET), "base", "cannot_connect"),
        (ValueError(SECRET), "host", "invalid_host"),
        (RuntimeError(SECRET), "base", "unknown"),
    ],
)
async def test_connection_error_and_recovery(hass, camera_client, mock_setup, caplog, error, field, message):
    result = await user_form(hass)
    camera_client.device_info.side_effect = error
    result = await hass.config_entries.flow.async_configure(result["flow_id"], DATA)
    assert result["errors"] == {field: message}
    assert_password_is_empty(result)
    assert SECRET not in caplog.text
    camera_client.device_info.side_effect = None
    result = await hass.config_entries.flow.async_configure(result["flow_id"], DATA)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == "TEST-SERIAL_1"


@pytest.mark.parametrize("host", ["", "http://camera", "camera/path", "user@camera", "camera?token=x"])
async def test_invalid_host_and_recovery(hass, camera_client, mock_setup, host):
    result = await user_form(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], DATA | {"host": host})
    assert result["errors"] == {"host": "invalid_host"}
    camera_client.device_info.assert_not_called()
    result = await hass.config_entries.flow.async_configure(result["flow_id"], DATA)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == "TEST-SERIAL_1"


async def test_missing_password_and_recovery(hass, camera_client, mock_setup):
    result = await user_form(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], DATA | {"password": ""})
    assert result["errors"] == {"password": "password_required"}
    camera_client.device_info.assert_not_called()
    result = await hass.config_entries.flow.async_configure(result["flow_id"], DATA)
    assert result["result"].unique_id == "TEST-SERIAL_1"


async def test_title_fallback_and_ipv6_normalization(hass, camera_client, mock_setup):
    camera_client.device_info.return_value = {"serialNumber": "TEST-SERIAL"}
    result = await user_form(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], DATA | {"host": " [2001:db8::10] "})
    assert result["title"] == "ISAPI Vision"
    assert result["data"]["host"] == "2001:db8::10"
    assert result["result"].unique_id == "TEST-SERIAL_1"


@pytest.mark.parametrize("source", [SOURCE_REAUTH, SOURCE_RECONFIGURE])
@pytest.mark.parametrize("password", [None, "", "New-Example-Password!"])
async def test_edit_connection_preserves_identity_and_secret(hass, camera_client, mock_setup, source, password):
    entry = MockConfigEntry(domain=DOMAIN, unique_id="TEST-SERIAL_1", data=DATA, title="Driveway")
    entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": source, "entry_id": entry.entry_id}, data=DATA if source == SOURCE_REAUTH else None
    )
    assert_password_is_empty(result)
    values = {key: value for key, value in DATA.items() if key != "password"}
    if password is not None:
        values["password"] = password
    result = await hass.config_entries.flow.async_configure(result["flow_id"], values)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == ("reauth_successful" if source == SOURCE_REAUTH else "reconfigure_successful")
    assert entry.unique_id == "TEST-SERIAL_1"
    assert entry.data["password"] == (password or SECRET)
    assert entry.title == "Driveway"
    await hass.async_block_till_done()


@pytest.mark.parametrize("source", [SOURCE_REAUTH, SOURCE_RECONFIGURE])
async def test_wrong_device_then_recovery(hass, camera_client, mock_setup, source):
    entry = MockConfigEntry(domain=DOMAIN, unique_id="TEST-SERIAL_1", data=DATA, title="Driveway")
    entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": source, "entry_id": entry.entry_id}, data=DATA if source == SOURCE_REAUTH else None
    )
    camera_client.device_info.return_value = {"serialNumber": "WRONG"}
    result = await hass.config_entries.flow.async_configure(result["flow_id"], DATA)
    assert result["errors"] == {"base": "wrong_device"}
    assert entry.data["password"] == SECRET
    camera_client.device_info.return_value = {"serialNumber": "TEST-SERIAL"}
    result = await hass.config_entries.flow.async_configure(result["flow_id"], DATA)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] in {"reauth_successful", "reconfigure_successful"}
    assert entry.unique_id == "TEST-SERIAL_1"
    await hass.async_block_till_done()


async def test_options_save_debounce_and_preserve_existing_settings(hass, mock_setup):
    entry = MockConfigEntry(domain=DOMAIN, unique_id="TEST-SERIAL_1", data=DATA, options={"scan_interval": 240})
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"alarm_hold": 0, "debounce_seconds": 15, "parameter_entities": False}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {"scan_interval": 240, "alarm_hold": 0, "debounce_seconds": 15, "parameter_entities": False}


async def test_invalid_options_then_recovery(hass):
    entry = MockConfigEntry(domain=DOMAIN, unique_id="TEST-SERIAL_1", data=DATA)
    entry.add_to_hass(hass)
    flow = IsapiVisionOptionsFlow()
    flow.hass = hass
    flow.handler = entry.entry_id
    result = await flow.async_step_init({"alarm_hold": 10, "debounce_seconds": -1, "parameter_entities": True})
    assert result["errors"] == {"base": "invalid_options"}
    result = await flow.async_step_init({"alarm_hold": 10, "debounce_seconds": 5, "parameter_entities": True})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"]["debounce_seconds"] == 5


async def test_password_is_passed_verbatim_including_spaces(hass, camera_client, mock_setup):
    result = await user_form(hass)
    password = "  Ünicode Example Password!  "
    with patch("custom_components.isapi_vision.config_flow.make_client", return_value=camera_client) as factory:
        result = await hass.config_entries.flow.async_configure(result["flow_id"], DATA | {"password": password})
    assert factory.call_args.args[1]["password"] == password
    assert result["data"]["password"] == password
    assert result["result"].unique_id == "TEST-SERIAL_1"
