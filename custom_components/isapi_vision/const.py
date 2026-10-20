"""Read-only ISAPI Vision constants."""

DOMAIN = "isapi_vision"
DEFAULT_OPTIONS = {"scan_interval": 120, "alarm_hold": 10, "debounce_seconds": 0, "parameter_entities": True}
DISCOVERY_RECHECK_SECONDS = 3600

# Endpoint support varies by hardware and firmware. These are GET requests only.
ENDPOINTS = {
    "device": "/ISAPI/System/deviceInfo",
    "capabilities": "/ISAPI/System/capabilities",
    "smart_capabilities": "/ISAPI/Smart/capabilities",
    "status": "/ISAPI/System/status",
    "time": "/ISAPI/System/time",
    "streams": "/ISAPI/Streaming/channels",
    "video": "/ISAPI/System/Video/inputs/channels/{channel}",
    "image": "/ISAPI/Image/channels/{channel}",
    "image_capabilities": "/ISAPI/Image/channels/{channel}/capabilities",
    "audio": "/ISAPI/System/Audio/channels",
    "motion": "/ISAPI/System/Video/inputs/channels/{channel}/motionDetection",
    "motion_capabilities": "/ISAPI/System/Video/inputs/channels/{channel}/motionDetection/capabilities",
    "tamper": "/ISAPI/System/Video/inputs/channels/{channel}/tamperDetection",
    "line_crossing": "/ISAPI/Intelligent/channels/{channel}/lineDetection",
    "intrusion": "/ISAPI/Intelligent/channels/{channel}/fieldDetection",
    "region_entrance": "/ISAPI/Intelligent/channels/{channel}/regionEntrance",
    "region_exit": "/ISAPI/Intelligent/channels/{channel}/regionExiting",
    "line_crossing_capabilities": "/ISAPI/Intelligent/channels/{channel}/lineDetection/capabilities",
    "intrusion_capabilities": "/ISAPI/Intelligent/channels/{channel}/fieldDetection/capabilities",
    "region_entrance_capabilities": "/ISAPI/Intelligent/channels/{channel}/regionEntrance/capabilities",
    "region_exit_capabilities": "/ISAPI/Intelligent/channels/{channel}/regionExiting/capabilities",
    "event_capabilities": "/ISAPI/Event/capabilities",
    "channel_event_capabilities": "/ISAPI/Event/channels/{channel}/capabilities",
    "event_triggers": "/ISAPI/Event/triggers",
    "motion_trigger": "/ISAPI/Event/triggers/VMD-{channel}",
    "tamper_trigger": "/ISAPI/Event/triggers/tamperDetection-{channel}",
    "storage": "/ISAPI/ContentMgmt/Storage",
    "recording": "/ISAPI/ContentMgmt/record/tracks",
    "alarm_inputs": "/ISAPI/System/IO/inputs",
    "alarm_outputs": "/ISAPI/System/IO/outputs",
    "network": "/ISAPI/System/Network/interfaces",
}

# (friendly name, icon, device class, enabled by default)
DETECTIONS = {
    "person": ("Person detected", "mdi:walk", "motion", True),
    "vehicle": ("Vehicle detected", "mdi:car", "motion", True),
    "motion": ("Motion detected", "mdi:motion-sensor", "motion", True),
    "line_crossing": ("Line crossing", "mdi:vector-line", "motion", True),
    "intrusion": ("Intrusion", "mdi:shield-alert", "motion", True),
    "region_entrance": ("Region entrance", "mdi:location-enter", "motion", True),
    "region_exit": ("Region exit", "mdi:location-exit", "motion", True),
    "tamper": ("Tampering", "mdi:shield-alert", "tamper", False),
    "video_loss": ("Video loss", "mdi:video-off", "problem", False),
    "disk_error": ("Storage error", "mdi:harddisk-alert", "problem", False),
    "disk_full": ("Storage full", "mdi:harddisk", "problem", False),
    "alarm_input": ("Alarm input", "mdi:alarm-light", None, False),
}

EVENT_MAP = {
    "vmd": "motion",
    "motiondetection": "motion",
    "linedetection": "line_crossing",
    "linecrossing": "line_crossing",
    "fielddetection": "intrusion",
    "intrusion": "intrusion",
    "regionentrance": "region_entrance",
    "regionexiting": "region_exit",
    "tamperdetection": "tamper",
    "shelteralarm": "tamper",
    "videoloss": "video_loss",
    "diskerror": "disk_error",
    "diskfull": "disk_full",
    "io": "alarm_input",
}

PERSISTENT_ALARMS = {"video_loss", "disk_error", "disk_full", "alarm_input"}

# Read-only alternatives are tried on the camera, never chosen by model/firmware.
SMART_PATH_NAMES = {
    "line_crossing": "LineDetection",
    "intrusion": "FieldDetection",
    "region_entrance": "RegionEntrance",
    "region_exit": "RegionExiting",
}
ENDPOINT_ALTERNATIVES = {}
for _feature, _name in SMART_PATH_NAMES.items():
    ENDPOINT_ALTERNATIVES[_feature] = (f"/ISAPI/Smart/{_name}/{{channel}}",)
    ENDPOINT_ALTERNATIVES[f"{_feature}_capabilities"] = (f"/ISAPI/Smart/{_name}/{{channel}}/capabilities",)
