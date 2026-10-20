"""Sanitized inventory; never export config entry data or event XML."""

from .discovery import feature_report


async def async_get_config_entry_diagnostics(hass, entry) -> dict:
    coordinator = entry.runtime_data
    return {
        "model": coordinator.data.device.get("model"),
        "firmware": coordinator.data.device.get("firmwareVersion"),
        "channel": coordinator.client.channel,
        "camera_connection": coordinator.last_update_success,
        "event_stream_connection": coordinator.stream_connected,
        "event_stream_error": coordinator.stream_error,
        "event_types_observed": sorted(coordinator.observed_event_types),
        "detectors_observed": sorted(coordinator.alarms.seen),
        "endpoint_status": coordinator.data.endpoints,
        "endpoint_probes": coordinator.data.probes,
        "features": feature_report(coordinator.features),
        "parameters": coordinator.data.parameters,
        "limits": {
            "xml_bytes_per_response": 1048576,
            "parameters_per_endpoint": 3000,
            "note": "Known endpoints only; credentials and network identifiers omitted. Long scalar values are marked.",
        },
    }
