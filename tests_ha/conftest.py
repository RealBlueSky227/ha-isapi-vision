"""Real Home Assistant fixtures; never connect to a physical camera in CI."""

from unittest.mock import AsyncMock, patch

import pytest


@pytest.fixture(autouse=True)
def custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture
def mock_setup():
    with patch("custom_components.isapi_vision.async_setup_entry", return_value=True) as setup:
        yield setup


@pytest.fixture
def camera_client():
    with patch("custom_components.isapi_vision.config_flow.make_client") as factory:
        factory.return_value.device_info = AsyncMock(
            return_value={"serialNumber": "TEST-SERIAL", "deviceName": "Driveway"}
        )
        yield factory.return_value
