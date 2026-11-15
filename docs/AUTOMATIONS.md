# Dashboard and automation examples

The [dashboard example](../examples/dashboard.yaml) uses standard HA cards and built-in icons. Match entity IDs to the installed device; existing labels and IDs are preserved across upgrades, so names may differ.

There are no custom services, device triggers or device conditions. Standard HA state triggers and conditions work with discovered sensors:

```yaml
triggers:
  - trigger: state
    entity_id: binary_sensor.driveway_person_detected
    to: "on"
conditions:
  - condition: state
    entity_id: binary_sensor.driveway_event_stream_connection
    state: "on"
actions:
  - action: persistent_notification.create
    data:
      title: Driveway
      message: The camera detected a person.
```

The off debounce affects sensor states and automations using them. The event entity remains immediate: trigger on changes of `event.driveway_camera_event` and inspect `camera_event_type`, `camera_event_state`, `targets`, `channel` and `rule`. Unknown accepted vendor alarms still appear there; heartbeats are excluded.

Discovered active-defense outputs use standard HA button actions. For example:

```yaml
actions:
  - action: button.press
    target:
      entity_id: button.driveway_sound_audible_alarm
```

The buttons are momentary and intentionally have no ON/OFF state. Pressing one can make the camera sound or flash immediately. Use conditions, rate limits and deliberate user confirmation appropriate to the installation. Use the snapshot camera entity for HA's standard camera actions. For live video, use a separate ONVIF/Generic Camera/Frigate entity. PTZ and persistent camera-setting writes are not available.
