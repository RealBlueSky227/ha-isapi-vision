import importlib
import unittest

from loader import protocol

discovery = importlib.import_module("isapi_vision_test.discovery")


def features(**payloads):
    return discovery.discover_features({key: protocol.parse_xml(value) for key, value in payloads.items()}, 1)


class DiscoveryTests(unittest.TestCase):
    def test_empty_capabilities_do_not_claim_absent_features_are_unsupported(self):
        result = features(
            channel_event_capabilities=b'<ChannelEventCap><eventType opt="VMD,tamperDetection"/><channelID>1</channelID></ChannelEventCap>'
        )
        self.assertEqual(result["motion"].support, "supported")
        self.assertEqual(result["tamper"].support, "supported")
        self.assertEqual(result["line_crossing"].support, "unknown")
        self.assertEqual(result["person"].support, "unknown")

    def test_explicit_true_false_and_missing_flags_differ(self):
        result = features(
            smart_capabilities=b"<SmartCap><isSupportLineDetection>true</isSupportLineDetection><isSupportFieldDetection>false</isSupportFieldDetection></SmartCap>"
        )
        self.assertEqual(result["line_crossing"].support, "supported")
        self.assertEqual(result["intrusion"].support, "unsupported")
        self.assertEqual(result["region_exit"].support, "unknown")
        self.assertIn("smart_capabilities:isSupportLineDetection=true", result["line_crossing"].evidence)

    def test_disabled_rule_is_supported_and_configuration_is_separate(self):
        result = features(line_crossing=b"<LineDetection><id>1</id><enabled>false</enabled></LineDetection>")
        self.assertEqual(result["line_crossing"].support, "supported")
        self.assertIs(result["line_crossing"].enabled, False)

    def test_target_capability_options_work_when_classification_disabled(self):
        result = features(
            motion_capabilities=b'<MotionDetection><targetType opt="human,vehicle">all</targetType></MotionDetection>',
            motion=b"<MotionDetection><enabled>false</enabled><targetType>human</targetType></MotionDetection>",
        )
        self.assertEqual(result["person"].support, "supported")
        self.assertEqual(result["vehicle"].support, "supported")
        self.assertIs(result["person"].enabled, False)
        self.assertIs(result["vehicle"].enabled, False)

    def test_target_current_filter_is_not_support_exclusion(self):
        result = features(
            motion_capabilities=b'<MotionDetection><targetType opt="human,vehicle"/></MotionDetection>',
            motion=b"<MotionDetection><enabled>true</enabled><targetType>human</targetType></MotionDetection>",
        )
        self.assertIs(result["person"].enabled, True)
        self.assertEqual(result["vehicle"].support, "supported")
        self.assertIs(result["vehicle"].enabled, False)

    def test_advertised_channel_events_can_override_global_false(self):
        result = features(
            smart_capabilities=b"<SmartCap><isSupportLineDetection>false</isSupportLineDetection></SmartCap>",
            channel_event_capabilities=b'<ChannelEventCap><channelID>1</channelID><eventType opt="lineDetection,fieldDetection,regionEntrance,regionExiting"/></ChannelEventCap>',
        )
        for key in ("line_crossing", "intrusion", "region_entrance", "region_exit"):
            self.assertEqual(result[key].support, "supported")
        self.assertEqual(len(result["line_crossing"].evidence), 2)

    def test_other_channel_capabilities_do_not_leak(self):
        result = features(
            channel_event_capabilities=b'<ChannelEventCap><channelID>2</channelID><eventType opt="lineDetection"/></ChannelEventCap>'
        )
        self.assertEqual(result["line_crossing"].support, "unknown")
        result = features(
            smart_capabilities=b"<SmartChannelCapList><SmartChannelCap><id>2</id><isSupportLineDetection>true</isSupportLineDetection></SmartChannelCap><SmartChannelCap><id>1</id><isSupportFieldDetection>true</isSupportFieldDetection></SmartChannelCap></SmartChannelCapList>"
        )
        self.assertEqual(result["line_crossing"].support, "unknown")
        self.assertEqual(result["intrusion"].support, "supported")

    def test_unknown_enable_state_and_namespace(self):
        result = features(line_crossing=b'<LineDetection xmlns="urn:firmware:any"><id>1</id></LineDetection>')
        self.assertEqual(result["line_crossing"].support, "supported")
        self.assertIsNone(result["line_crossing"].enabled)

    def test_explicit_generic_capability_rejection_is_not_readable_support(self):
        result = features(
            line_crossing_capabilities=b"<LineDetectionCap><isSupport>false</isSupport></LineDetectionCap>"
        )
        self.assertEqual(result["line_crossing"].support, "unsupported")

    def test_unrelated_xml_is_not_a_working_feature(self):
        self.assertFalse(discovery.valid_feature_document("line_crossing", protocol.parse_xml(b"<DeviceInfo/>")))
        result = features(line_crossing=b"<DeviceInfo/>")
        self.assertEqual(result["line_crossing"].support, "unknown")

    def test_feature_specific_capability_false_is_not_readable_support(self):
        result = features(
            line_crossing_capabilities=b"<LineDetectionCap><isSupportLineDetection>false</isSupportLineDetection></LineDetectionCap>"
        )
        self.assertEqual(result["line_crossing"].support, "unsupported")

    def test_other_channel_configuration_is_not_support_for_selected_channel(self):
        result = features(
            line_crossing=b"<LineDetectionList><LineDetection><id>2</id><enabled>true</enabled></LineDetection></LineDetectionList>"
        )
        self.assertEqual(result["line_crossing"].support, "unknown")

    def test_real_event_confirms_omitted_or_negative_capability(self):
        info = discovery.FeatureInfo("unsupported", False, ("capability:false",)).observed()
        self.assertEqual(info.support, "supported")
        self.assertIs(info.enabled, False)
        self.assertIn("event_stream", info.evidence)

    def test_firmware_and_model_have_no_influence(self):
        for name in (b"FCD600", b"CompletelyUnknownCamera"):
            result = features(
                device=b"<DeviceInfo><model>"
                + name
                + b"</model><firmwareVersion>anything</firmwareVersion></DeviceInfo>"
            )
            self.assertTrue(all(info.support == "unknown" for info in result.values()))
