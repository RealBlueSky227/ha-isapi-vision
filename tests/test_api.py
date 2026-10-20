import asyncio
import hashlib
import re
import unittest
from collections import Counter

from aiohttp import ClientSession, web
from loader import api
from test_protocol import event_xml

DEVICE = b"<DeviceInfo><deviceName>Driveway</deviceName><model>FCD600</model><serialNumber>TEST123</serialNumber><firmwareVersion>V5.test</firmwareVersion></DeviceInfo>"


class CameraServerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.counts = Counter()
        self.methods = set()
        self.overrides = {}
        self.stream_opened = asyncio.Event()
        self.stream_release = asyncio.Event()
        self.keep_stream = False
        self.valid_auths = 0
        app = web.Application()
        app.router.add_route("*", "/{path:.*}", self.handle)
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, "127.0.0.1", 0)
        await site.start()
        self.port = site._server.sockets[0].getsockname()[1]
        self.session = ClientSession()
        self.client = api.IsapiVisionClient(self.session, "127.0.0.1", "tester", "test-only", self.port)

    async def asyncTearDown(self):
        self.stream_release.set()
        await self.session.close()
        await self.runner.cleanup()

    def authenticated(self, request):
        header = request.headers.get("Authorization", "")
        if not header.startswith("Digest "):
            return False
        parts = dict(
            (match[0], match[1] or match[2]) for match in re.findall(r'(\w+)=(?:"([^"]*)"|([^, ]+))', header[7:])
        )

        def md5(value):
            return hashlib.md5(value.encode()).hexdigest()

        expected = md5(
            ":".join(
                [
                    md5("tester:Camera:test-only"),
                    "fixednonce",
                    parts.get("nc", ""),
                    parts.get("cnonce", ""),
                    "auth",
                    md5(f"{request.method}:{request.path}"),
                ]
            )
        )
        return parts.get("response") == expected

    async def handle(self, request):
        self.methods.add(request.method)
        if not self.authenticated(request):
            return web.Response(
                status=401,
                headers={"WWW-Authenticate": 'Digest realm="Camera", nonce="fixednonce", algorithm=MD5, qop="auth"'},
            )
        self.valid_auths += 1
        self.counts[request.path] += 1
        if request.path in self.overrides:
            status, data = self.overrides[request.path]
            return web.Response(status=status, body=data)
        if request.path == "/ISAPI/System/deviceInfo":
            return web.Response(body=DEVICE, content_type="application/xml")
        if request.path == "/ISAPI/Streaming/channels/101/picture":
            return web.Response(body=b"\xff\xd8fake-jpeg\xff\xd9", content_type="image/jpeg")
        if request.path == "/ISAPI/Event/notification/alertStream":
            response = web.StreamResponse(headers={"Content-Type": "multipart/mixed; boundary=boundary"})
            await response.prepare(request)
            await response.write(b"--boundary\r\nContent-Type: application/xml\r\n\r\n" + event_xml()[:80])
            await response.write(event_xml()[80:])
            self.stream_opened.set()
            if self.keep_stream:
                await self.stream_release.wait()
            await response.write_eof()
            return response
        if request.path == "/ISAPI/System/status":
            return web.Response(
                body=b"<DeviceStatus><deviceUpTime>100</deviceUpTime><password>never-export-this</password></DeviceStatus>"
            )
        return web.Response(status=404)

    async def test_real_digest_handshake_and_device_identity(self):
        info = await self.client.device_info()
        self.assertEqual(info["model"], "FCD600")
        self.assertEqual(info["serialNumber"], "TEST123")
        self.assertEqual(self.valid_auths, 1)
        self.assertEqual(self.methods, {"GET"})

    async def test_export_does_not_expose_credentials_echoed_in_unsuspicious_fields(self):
        self.overrides["/ISAPI/System/status"] = (
            200,
            b"<DeviceStatus><description>test-only</description><comment>tester</comment><note>127.0.0.1</note></DeviceStatus>",
        )
        result = await self.client.inventory()
        self.assertNotIn("test-only", repr(result.parameters))
        self.assertNotIn("tester", repr(result.parameters))
        self.assertNotIn("127.0.0.1", repr(result.parameters))

    async def test_bad_password_reports_auth_error(self):
        self.client._password = "incorrect-test-password"
        with self.assertRaises(api.CameraAuthError):
            await self.client.device_info()

    async def test_required_permission_failure_reports_auth_error(self):
        self.overrides["/ISAPI/System/deviceInfo"] = (403, b"Forbidden")
        with self.assertRaises(api.CameraAuthError):
            await self.client.device_info()

    async def test_requires_actual_device_identity(self):
        for payload in (b"<DeviceInfo><model>FCD600</model></DeviceInfo>", b"<html>login</html>"):
            self.overrides["/ISAPI/System/deviceInfo"] = (200, payload)
            with self.assertRaises(api.CameraError):
                await self.client.device_info()

    async def test_inventory_scrubs_fields_skips_unsupported_and_retries_forbidden(self):
        self.overrides["/ISAPI/System/Audio/channels"] = (403, b"Forbidden")
        inventory = await self.client.inventory()
        self.assertEqual(inventory.parameters, {"status/DeviceStatus/deviceUpTime": "100"})
        self.assertEqual(inventory.endpoints["image"], "unsupported")
        self.assertEqual(inventory.endpoints["audio"], "permission_denied")
        await self.client.inventory()
        self.assertEqual(self.counts["/ISAPI/Image/channels/1"], 1)
        self.assertEqual(self.counts["/ISAPI/System/Audio/channels"], 2)
        self.assertEqual(self.methods, {"GET"})

    async def test_disappearing_parameter_is_not_retained(self):
        self.assertTrue((await self.client.inventory()).parameters)
        self.overrides["/ISAPI/System/status"] = (500, b"error")
        result = await self.client.inventory()
        self.assertEqual(result.parameters, {})
        self.assertEqual(result.endpoints["status"], "http_500")

    async def test_error_xml_and_invalid_xml_report_unavailable(self):
        for payload in (b"<ResponseStatus><statusCode>4</statusCode></ResponseStatus>", b"<bad"):
            self.overrides["/ISAPI/System/status"] = (200, payload)
            result = await self.client.inventory()
            self.assertEqual(result.endpoints["status"], "unavailable_or_invalid_response")

    async def test_snapshot_validates_image(self):
        self.assertTrue((await self.client.snapshot()).startswith(b"\xff\xd8"))
        self.overrides["/ISAPI/Streaming/channels/101/picture"] = (200, b"<error/>")
        with self.assertRaises(api.CameraError):
            await self.client.snapshot()

    async def test_substream_snapshot_works_when_main_stream_busy(self):
        self.overrides["/ISAPI/Streaming/channels/101/picture"] = (503, b"<busy/>")
        self.overrides["/ISAPI/Streaming/channels/102/picture"] = (200, b"\xff\xd8substream\xff\xd9")
        self.assertIn(b"substream", await self.client.snapshot())
        self.assertEqual(self.counts["/ISAPI/Streaming/channels/101/picture"], 0)

    async def test_403_not_supported_is_distinct_from_permission_denied(self):
        self.overrides["/ISAPI/System/Audio/channels"] = (
            403,
            b"<ResponseStatus><subStatusCode>notSupport</subStatusCode></ResponseStatus>",
        )
        result = await self.client.inventory()
        self.assertEqual(result.endpoints["audio"], "unsupported")

    async def test_smart_alternate_endpoint_discovers_a_disabled_feature(self):
        self.overrides["/ISAPI/Smart/LineDetection/1"] = (
            200,
            b"<LineDetection><id>1</id><enabled>false</enabled></LineDetection>",
        )
        result = await self.client.inventory()
        self.assertEqual(result.endpoints["line_crossing"], "ok")
        self.assertEqual(result.features["line_crossing"].support, "supported")
        self.assertIs(result.features["line_crossing"].enabled, False)
        self.assertEqual(result.probes["line_crossing"]["/ISAPI/Intelligent/channels/1/lineDetection"], "unsupported")
        await self.client.inventory()
        self.assertEqual(self.counts["/ISAPI/Intelligent/channels/1/lineDetection"], 1)
        self.assertEqual(self.counts["/ISAPI/Smart/LineDetection/1"], 2)

    async def test_capability_advertisement_works_without_configuration_permission(self):
        self.overrides["/ISAPI/Smart/capabilities"] = (
            200,
            b"<SmartCap><isSupportLineDetection>true</isSupportLineDetection></SmartCap>",
        )
        self.overrides["/ISAPI/Smart/LineDetection/1"] = (403, b"Forbidden")
        result = await self.client.inventory()
        self.assertEqual(result.features["line_crossing"].support, "supported")
        self.assertEqual(result.endpoints["line_crossing"], "permission_denied")

    async def test_permission_and_missing_paths_leave_feature_unknown(self):
        self.overrides["/ISAPI/Smart/LineDetection/1"] = (403, b"Forbidden")
        result = await self.client.inventory()
        self.assertEqual(result.features["line_crossing"].support, "unknown")
        self.assertEqual(result.features["intrusion"].support, "unknown")

    async def test_discovery_rechecks_cached_missing_paths(self):
        await self.client.inventory()
        self.overrides["/ISAPI/Intelligent/channels/1/lineDetection"] = (
            200,
            b"<LineDetection><enabled>true</enabled></LineDetection>",
        )
        self.client._rediscover_at = 0
        result = await self.client.inventory()
        self.assertEqual(result.features["line_crossing"].support, "supported")
        self.assertEqual(self.counts["/ISAPI/Intelligent/channels/1/lineDetection"], 2)

    async def test_invalid_xml_root_does_not_create_detector(self):
        self.overrides["/ISAPI/Smart/LineDetection/1"] = (200, b"<DeviceInfo/>")
        result = await self.client.inventory()
        self.assertEqual(result.features["line_crossing"].support, "unknown")
        self.assertEqual(result.endpoints["line_crossing"], "unavailable_or_invalid_response")

    async def test_stream_split_xml_and_eof(self):
        events = []
        connected = []
        with self.assertRaises(api.CameraError):
            async for event in self.client.events(lambda: connected.append(True)):
                events.append(event)
        self.assertEqual(len(connected), 1)
        self.assertEqual(events[0].targets, {"person"})

    async def test_stream_cancel_closes_connection(self):
        self.keep_stream = True
        received = asyncio.Event()

        async def consume():
            async for _event in self.client.events(lambda: None):
                received.set()

        task = asyncio.create_task(consume())
        await asyncio.wait_for(received.wait(), 2)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.stream_release.set()

    async def test_redirects_are_not_followed(self):
        self.overrides["/ISAPI/System/deviceInfo"] = (302, b"Moved")
        with self.assertRaises(api.EndpointError):
            await self.client.device_info()

    async def test_oversized_body_rejected(self):
        self.overrides["/ISAPI/System/deviceInfo"] = (200, b"x" * (1024 * 1024 + 1))
        with self.assertRaises(api.CameraError):
            await self.client.device_info()
