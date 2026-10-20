import unittest

from loader import protocol as p


def event_xml(
    kind="VMD", state="active", target="human", namespace="http://www.std-cgi.com/ver20/XMLSchema", channel=1
):
    return (
        f'<EventNotificationAlert xmlns="{namespace}"><eventType>{kind}</eventType>'
        f"<eventState>{state}</eventState><channelID>{channel}</channelID>"
        f"<targetType>{target}</targetType></EventNotificationAlert>"
    ).encode()


class ParserTests(unittest.TestCase):
    def test_credentials_echoed_in_values_attributes_or_identifiers_are_redacted(self):
        root = p.parse_xml(
            b'<Settings><description>pw-example</description><mode opt="pw-example">day</mode><Item><id>pw-example</id><value>ok</value></Item><Item><id>2</id><value>ok</value></Item><key>hidden</key><PSK>hidden</PSK><passphrase>hidden</passphrase></Settings>'
        )
        result = p.flatten(root, ("pw-example",))
        self.assertNotIn("pw-example", repr(result))
        self.assertNotIn("hidden", repr(result))
        self.assertIn("[redacted]", repr(result))

    def test_every_byte_chunk_and_multibyte(self):
        payload = event_xml(target="human")
        parser = p.AlertParser()
        events = []
        for byte in b"--boundary\r\nContent-Type: application/xml\r\n" + payload:
            events.extend(parser.feed(bytes([byte])))
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].targets, {"person"})

    def test_namespace_variants_nested_targets_and_prefix(self):
        for namespace in ("http://www.isapi.org/ver20/XMLSchema", "", "urn:vendor:v3"):
            event = p.parse_event(p.parse_xml(event_xml(namespace=namespace)))
            self.assertEqual(event.targets, {"person"})
        payload = b'<n:EventNotificationAlert xmlns:n="urn:x"><n:eventType>lineDetection</n:eventType><n:eventState>active</n:eventState><n:DetectionRegionList><n:detectionTarget>human,vehicle</n:detectionTarget></n:DetectionRegionList></n:EventNotificationAlert>'
        event = p.AlertParser().feed(payload)[0]
        self.assertEqual(event.targets, {"person", "vehicle"})

    def test_multiple_documents_images_and_malformed_document(self):
        payload = (
            b"\xff\xd8"
            + event_xml()
            + b"<EventNotificationAlert><broken></EventNotificationAlert>"
            + event_xml(target="vehicle")
        )
        events = p.AlertParser().feed(payload)
        self.assertEqual([event.targets for event in events], [{"person"}, {"vehicle"}])

    def test_bounded_unfinished_xml_and_garbage(self):
        parser = p.AlertParser()
        parser.feed(b"x" * (p.MAX_XML * 2))
        self.assertLessEqual(len(parser.buffer), 128)
        parser.feed(b"<EventNotificationAlert>" + b"x" * p.MAX_XML)
        self.assertLessEqual(len(parser.buffer), 128)
        self.assertEqual(len(parser.feed(event_xml())), 1)

    def test_doctype_and_expansion_rejected(self):
        with self.assertRaises(ValueError):
            p.parse_xml(b'<!DOCTYPE x [<!ENTITY a "secret">]><x>&a;</x>')

    def test_flatten_scrubs_sensitive_subtrees_and_attributes(self):
        root = p.parse_xml(
            b'<Config password="secret"><Network><ipAddress>private</ipAddress></Network><username>admin</username><Credentials><value>secret</value></Credentials><mode opt="day,night">day</mode><streamURI>rtsp://secret</streamURI><serialNumber>unique</serialNumber></Config>'
        )
        self.assertEqual(p.flatten(root), {"Config/mode/@opt": "day,night", "Config/mode": "day"})

    def test_repeated_nodes_stable_when_order_changes(self):
        first = p.flatten(
            p.parse_xml(
                b"<Streams><Channel><id>101</id><fps>20</fps></Channel><Channel><id>102</id><fps>10</fps></Channel></Streams>"
            )
        )
        second = p.flatten(
            p.parse_xml(
                b"<Streams><Channel><id>102</id><fps>10</fps></Channel><Channel><id>101</id><fps>20</fps></Channel></Streams>"
            )
        )
        self.assertEqual(first, second)
        self.assertEqual(first["Streams/Channel[id=101]/fps"], "20")

    def test_long_scalars_and_depth_are_bounded(self):
        root = p.parse_xml(b"<x><value>" + b"a" * 256 + b"</value></x>")
        self.assertLessEqual(len(p.flatten(root)["x/value"]), 255)
        with self.assertRaises(ValueError):
            p.parse_xml(b"<x>" * 100 + b"value" + b"</x>" * 100)

    def test_dtd_rejected_in_all_supported_encodings_and_external_entities(self):
        documents = [
            '<!DOCTYPE x [<!ENTITY a "secret">]><x>&a;</x>',
            '<!DOCTYPE x SYSTEM "file:///must-not-read"><x/>',
            '<!DOCTYPE x [<!ENTITY % p SYSTEM "https://must-not-fetch">%p;]><x/>',
        ]
        for document in documents:
            for encoding in ("utf-8", "utf-16", "utf-16-le", "utf-16-be"):
                with self.subTest(document=document, encoding=encoding), self.assertRaises(ValueError):
                    p.parse_xml(document.encode(encoding))

    def test_node_limit_and_predefined_entities(self):
        with self.assertRaises(ValueError):
            p.parse_xml(b"<root>" + b"<x/>" * p.MAX_XML_NODES + b"</root>")
        self.assertEqual(p.parse_xml(b"<x>left &amp; right</x>").text, "left & right")


class AlarmTests(unittest.TestCase):
    def setUp(self):
        self.alarms = p.AlarmState(channel=1, hold=10)

    def apply(self, kind="VMD", state="active", target="human", now=0, channel=1):
        self.alarms.apply(p.parse_event(p.parse_xml(event_xml(kind, state, target, channel=channel))), now)

    def test_person_vehicle_motion_separate(self):
        self.apply()
        self.assertTrue(self.alarms.is_on("person"))
        self.assertTrue(self.alarms.is_on("motion"))
        self.assertFalse(self.alarms.is_on("vehicle"))

    def test_missing_inactive_repeated_activity_and_expiry(self):
        self.apply(now=0)
        self.apply(now=8)
        self.alarms.expire(11)
        self.assertTrue(self.alarms.is_on("person"))
        self.alarms.expire(18)
        self.assertFalse(self.alarms.is_on("person"))

    def test_inactive_without_classification_clears_its_source(self):
        self.apply()
        self.apply(state="inactive", target="")
        self.assertFalse(self.alarms.is_on("person"))
        self.assertFalse(self.alarms.is_on("motion"))

    def test_independent_event_sources_and_rules(self):
        self.apply()
        self.apply(kind="lineDetection")
        self.apply(state="inactive", target="")
        self.assertTrue(self.alarms.is_on("person"))
        self.apply(kind="lineDetection", state="inactive", target="")
        self.assertFalse(self.alarms.is_on("person"))
        for rule in ("1", "2"):
            self.alarms.apply(p.CameraEvent("vmd", "active", "1", frozenset({"person"}), rule), 0)
        self.alarms.apply(p.CameraEvent("vmd", "inactive", "1", frozenset(), "1"), 1)
        self.assertTrue(self.alarms.is_on("person"))

    def test_target_specific_inactive_leaves_vehicle_active(self):
        self.apply()
        self.apply(target="vehicle")
        self.apply(state="inactive", target="human")
        self.assertFalse(self.alarms.is_on("person"))
        self.assertTrue(self.alarms.is_on("vehicle"))
        self.assertTrue(self.alarms.is_on("motion"))

    def test_faults_wait_for_inactive_and_video_loss_recovers(self):
        self.apply(kind="diskerror", target="")
        self.apply(kind="videoloss", target="")
        self.alarms.expire(100)
        self.assertTrue(self.alarms.is_on("disk_error"))
        self.assertTrue(self.alarms.is_on("video_loss"))
        self.apply(kind="videoloss", state="inactive", target="")
        self.assertFalse(self.alarms.is_on("video_loss"))
        self.apply(kind="diskerror", state="inactive", target="")
        self.assertFalse(self.alarms.is_on("disk_error"))

    def test_other_channel_and_unknown_state_do_not_change_state(self):
        self.apply(channel=2)
        self.apply(state="unknown")
        self.assertFalse(self.alarms.is_on("person"))

    def test_heartbeat_does_not_replace_last_event(self):
        self.apply()
        self.apply(kind="videoloss", state="inactive", target="")
        self.assertEqual(self.alarms.last_event, "vmd")

    def test_disconnect_clear(self):
        self.apply()
        self.alarms.clear()
        self.assertFalse(self.alarms.is_on("person"))
