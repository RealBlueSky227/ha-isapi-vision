"""Async camera client with Digest authentication and bounded output tests."""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from xml.etree.ElementTree import Element

from aiohttp import ClientConnectorCertificateError, ClientError, ClientSession, ClientTimeout, DigestAuthMiddleware
from yarl import URL

from .const import DISCOVERY_RECHECK_SECONDS, ENDPOINT_ALTERNATIVES, ENDPOINTS
from .discovery import FeatureInfo, discover_features, valid_feature_document
from .protocol import MAX_XML, AlertParser, CameraEvent, flatten, local_name, parse_xml, text


class CameraError(Exception):
    """Camera communication or protocol failure."""


class CameraAuthError(CameraError):
    """Camera rejected credentials or required device access."""


class CameraCertificateError(CameraError):
    """The camera's HTTPS certificate could not be verified."""


class EndpointError(CameraError):
    def __init__(self, status: int, substatus: str | None = None) -> None:
        super().__init__(f"Camera HTTP status {status}")
        self.status = status
        self.substatus = substatus


@dataclass
class Inventory:
    device: dict[str, str]
    parameters: dict[str, str]
    endpoints: dict[str, str]
    features: dict[str, FeatureInfo] = field(default_factory=dict)
    probes: dict[str, dict[str, str]] = field(default_factory=dict)
    controls: dict[str, OutputControl] = field(default_factory=dict)


@dataclass(frozen=True)
class OutputControl:
    paths: tuple[str, ...]
    evidence: str


class IsapiVisionClient:
    def __init__(
        self,
        session: ClientSession,
        host: str,
        username: str,
        password: str,
        port: int = 80,
        use_ssl: bool = False,
        channel: int = 1,
    ) -> None:
        self.session = session
        self.base_url = URL.build(scheme="https" if use_ssl else "http", host=host, port=port)
        self._username = username
        self._password = password
        self.channel = channel
        self._unsupported: set[str] = set()
        self._resolved_paths: dict[str, str] = {}
        self._last_controls: dict[str, OutputControl] = {}
        self._rediscover_at = 0.0
        self._snapshot_stream = channel * 100 + 2

    def _request(self, path: str, stream: bool = False, method: str = "GET"):
        # A separate middleware per request avoids cross-request nonce races.
        relative = URL(path)
        url = self.base_url.with_path(relative.path).with_query(relative.query)
        return self.session.request(
            method,
            url,
            middlewares=(DigestAuthMiddleware(self._username, self._password),),
            timeout=ClientTimeout(total=None if stream else 12, sock_connect=8, sock_read=60 if stream else 10),
            allow_redirects=False,
        )

    @staticmethod
    def _check_status(status: int, payload: bytes = b"") -> None:
        if status == 401:
            raise CameraAuthError("Camera rejected authentication")
        if status != 200:
            substatus = None
            if payload:
                try:
                    substatus = text(parse_xml(payload), "subStatusCode")
                except ValueError:
                    pass
            raise EndpointError(status, substatus)

    async def _read(self, path: str, limit: int = MAX_XML) -> bytes:
        try:
            async with self._request(path) as response:
                if response.status != 200:
                    self._check_status(response.status, await response.content.read(8192))
                data = bytearray()
                async for chunk in response.content.iter_chunked(8192):
                    data.extend(chunk)
                    if len(data) > limit:
                        raise CameraError("Camera response exceeds size limit")
                return bytes(data)
        except ClientConnectorCertificateError as err:
            raise CameraCertificateError("Camera HTTPS certificate could not be verified") from err
        except (ClientError, TimeoutError) as err:
            raise CameraError("Camera request failed") from err

    async def _json(self, path: str) -> dict:
        try:
            payload = json.loads((await self._read(path)).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as err:
            raise CameraError("Camera returned invalid JSON") from err
        if not isinstance(payload, dict):
            raise CameraError("Camera returned an unexpected JSON document")
        return payload

    async def _put(self, path: str) -> None:
        try:
            async with self._request(path, method="PUT") as response:
                payload = await response.content.read(65536)
                self._check_status(response.status, payload)
                if payload:
                    try:
                        status = json.loads(payload.decode("utf-8"))
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        status = None
                    if isinstance(status, dict):
                        substatus = str(status.get("subStatusCode", "ok"))
                        if substatus.lower() not in {"ok", "success"}:
                            raise EndpointError(response.status, substatus)
        except ClientConnectorCertificateError as err:
            raise CameraCertificateError("Camera HTTPS certificate could not be verified") from err
        except (ClientError, TimeoutError) as err:
            raise CameraError("Camera output command failed") from err

    async def xml(self, path: str) -> Element:
        try:
            root = parse_xml(await self._read(path))
        except ValueError as err:
            raise CameraError("Camera returned invalid XML") from err
        if local_name(root.tag) == "ResponseStatus":
            if (substatus := text(root, "subStatusCode")) in {"notSupport", "methodNotAllowed"}:
                raise EndpointError(200, substatus)
            raise CameraError("Camera returned ISAPI error XML")
        return root

    async def device_info(self) -> dict[str, str]:
        try:
            root = await self.xml(ENDPOINTS["device"])
        except EndpointError as err:
            if err.status == 403:
                raise CameraAuthError("Account cannot read camera information") from err
            raise
        if local_name(root.tag) != "DeviceInfo":
            raise CameraError("Device does not provide ISAPI device information")
        result = {
            key: value
            for key in ("deviceName", "model", "serialNumber", "firmwareVersion", "firmwareReleasedDate")
            if (value := text(root, key))
        }
        if not result.get("serialNumber"):
            raise CameraError("Camera did not report a stable serial number")
        return result

    async def inventory(self) -> Inventory:
        device = await self.device_info()
        if time.monotonic() >= self._rediscover_at:
            self._unsupported.clear()
            self._rediscover_at = time.monotonic() + DISCOVERY_RECHECK_SECONDS
        parameters: dict[str, str] = {}
        statuses = {"device": "ok"}
        documents: dict[str, Element] = {}
        probes: dict[str, dict[str, str]] = {}
        semaphore = asyncio.Semaphore(2)

        async def fetch(key: str, path: str) -> None:
            candidates = dict.fromkeys([self._resolved_paths[key]] if key in self._resolved_paths else [])
            candidates.update(
                dict.fromkeys(
                    template.format(channel=self.channel) for template in (path, *ENDPOINT_ALTERNATIVES.get(key, ()))
                )
            )
            attempts = probes[key] = {}
            async with semaphore:
                for candidate in candidates:
                    if candidate in self._unsupported:
                        attempts[candidate] = "unsupported"
                        continue
                    try:
                        root = await self.xml(candidate)
                        if not valid_feature_document(key, root):
                            raise CameraError("Unrelated XML returned from feature endpoint")
                        documents[key] = root
                        parameters.update(
                            {
                                f"{key}/{name}": value
                                for name, value in flatten(
                                    root, (self._password, self._username, self.base_url.host or "")
                                ).items()
                            }
                        )
                        attempts[candidate] = "ok"
                        statuses[key] = "ok"
                        self._resolved_paths[key] = candidate
                        return
                    except EndpointError as err:
                        state = "permission_denied" if err.status == 403 else f"http_{err.status}"
                        if err.status in {404, 405, 501} or err.substatus in {"notSupport", "methodNotAllowed"}:
                            self._unsupported.add(candidate)
                            state = "unsupported"
                        attempts[candidate] = state
                    except CameraAuthError:
                        # Individual API areas may have different permissions.
                        attempts[candidate] = "authentication_denied"
                    except CameraError:
                        attempts[candidate] = "unavailable_or_invalid_response"
                errors = set(attempts.values()) - {"unsupported"}
                statuses[key] = next(
                    (
                        state
                        for state in ("authentication_denied", "permission_denied", "unavailable_or_invalid_response")
                        if state in errors
                    ),
                    sorted(errors)[0] if errors else "unsupported",
                )

        tasks = [asyncio.create_task(fetch(key, path)) for key, path in ENDPOINTS.items() if key != "device"]
        try:
            async with asyncio.timeout(55):
                await asyncio.gather(*tasks)
        except TimeoutError:
            for key in ENDPOINTS:
                statuses.setdefault(key, "poll_timeout")
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
        controls = await self._discover_output_controls(statuses, probes)
        self._last_controls = controls
        return Inventory(
            device, parameters, statuses, discover_features(documents, self.channel, probes), probes, controls
        )

    async def _discover_output_controls(
        self, statuses: dict[str, str], probes: dict[str, dict[str, str]]
    ) -> dict[str, OutputControl]:
        """Discover active-defense hardware with GET requests only."""

        async def read_first(key: str, candidates: tuple[str, ...]) -> tuple[dict | None, str | None]:
            attempts = probes[key] = {}
            for path in candidates:
                if path in self._unsupported:
                    attempts[path] = "unsupported"
                    continue
                try:
                    result = await self._json(path)
                    attempts[path] = "ok"
                    statuses[key] = "ok"
                    return result, path
                except EndpointError as err:
                    state = "permission_denied" if err.status == 403 else f"http_{err.status}"
                    if err.status in {404, 405, 501} or err.substatus in {"notSupport", "methodNotAllowed"}:
                        state = "unsupported"
                        self._unsupported.add(path)
                    attempts[path] = state
                except CameraAuthError:
                    attempts[path] = "authentication_denied"
                except CameraError:
                    attempts[path] = "unavailable_or_invalid_response"
            statuses[key] = next((state for state in attempts.values() if state != "unsupported"), "unsupported")
            return None, None

        channel = self.channel
        requests = (
            read_first(
                "audio_alarm_capabilities",
                ("/ISAPI/Event/triggers/notifications/AudioAlarm/capabilities?format=json",),
            ),
            read_first("audio_alarm", ("/ISAPI/Event/triggers/notifications/AudioAlarm?format=json",)),
            read_first(
                "flashing_alarm_capabilities",
                (
                    f"/ISAPI/Event/triggers/notifications/channels/{channel}/whiteLightAlarm/capabilities?format=json",
                    "/ISAPI/Event/triggers/notifications/whiteLightAlarm/capabilities?format=json",
                ),
            ),
            read_first(
                "flashing_alarm",
                (
                    f"/ISAPI/Event/triggers/notifications/channels/{channel}/whiteLightAlarm?format=json",
                    "/ISAPI/Event/triggers/notifications/whiteLightAlarm?format=json",
                ),
            ),
        )
        try:
            async with asyncio.timeout(20):
                (
                    (audio_caps, _),
                    (audio_config, _),
                    (strobe_caps, strobe_cap_path),
                    (
                        strobe_config,
                        strobe_config_path,
                    ),
                ) = await asyncio.gather(*requests)
        except TimeoutError:
            for key in ("audio_alarm_capabilities", "audio_alarm", "flashing_alarm_capabilities", "flashing_alarm"):
                statuses.setdefault(key, "poll_timeout")
            return {}

        controls: dict[str, OutputControl] = {}
        audio_id = self._find_json_value(audio_config, "audioID")
        if (
            self._find_json_value(audio_caps, "isSupportAudioTest") is True
            and isinstance(audio_id, int)
            and not isinstance(audio_id, bool)
        ):
            controls["audible_alarm"] = OutputControl(
                (f"/ISAPI/Event/triggers/notifications/AudioAlarm/{audio_id}/test?format=json",),
                f"isSupportAudioTest=true; selected audioID={audio_id}",
            )
        if strobe_caps is not None and strobe_config is not None and strobe_config_path is not None:
            base = strobe_config_path.split("?", 1)[0]
            controls["flashing_alarm"] = OutputControl(
                tuple(
                    dict.fromkeys(
                        (
                            f"{base}/test?format=json",
                            f"/ISAPI/Event/triggers/notifications/channels/{channel}/whiteLightAlarm/test?format=json",
                            "/ISAPI/Event/triggers/notifications/whiteLightAlarm/test?format=json",
                        )
                    )
                ),
                f"readable capability and configuration ({strobe_cap_path})",
            )
        return controls

    @staticmethod
    def _find_json_value(document: object, wanted: str) -> object | None:
        if isinstance(document, dict):
            for key, value in document.items():
                if key.casefold() == wanted.casefold():
                    return value
                if (result := IsapiVisionClient._find_json_value(value, wanted)) is not None:
                    return result
        elif isinstance(document, list):
            for value in document:
                if (result := IsapiVisionClient._find_json_value(value, wanted)) is not None:
                    return result
        return None

    async def activate_output(self, key: str) -> None:
        """Run a discovered momentary output test, trying firmware path variants."""
        control = getattr(self, "_last_controls", {}).get(key)
        if control is None:
            raise CameraError("Camera output is not currently available")
        last_error: CameraError | None = None
        for path in control.paths:
            try:
                await self._put(path)
                return
            except EndpointError as err:
                last_error = err
                if err.status not in {404, 405, 501} and err.substatus not in {"notSupport", "methodNotAllowed"}:
                    raise
            except CameraError as err:
                last_error = err
                raise
        raise last_error or CameraError("Camera rejected output command")

    async def snapshot(self) -> bytes:
        # This FCD600 firmware returns 503 for main-stream pictures; prefer substream.
        candidates = dict.fromkeys([self._snapshot_stream, self.channel * 100 + 2, self.channel * 100 + 1])
        last_error = CameraError("No snapshot stream available")
        for stream in candidates:
            try:
                data = await self._read(f"/ISAPI/Streaming/channels/{stream}/picture", 8 * MAX_XML)
                if not data.startswith(b"\xff\xd8"):
                    raise CameraError("Camera did not return a JPEG snapshot")
                self._snapshot_stream = stream
                return data
            except CameraAuthError:
                raise
            except CameraError as err:
                last_error = err
        raise last_error

    async def events(self, connected: Callable[[], None]) -> AsyncIterator[CameraEvent]:
        parser = AlertParser()
        try:
            async with self._request("/ISAPI/Event/notification/alertStream", stream=True) as response:
                if response.status != 200:
                    self._check_status(response.status, await response.content.read(8192))
                if "html" in response.headers.get("Content-Type", "").lower():
                    raise CameraError("Camera returned a web page instead of an alert stream")
                # Mark connected only after receiving a valid event/heartbeat XML document.
                verified = False
                async for chunk in response.content.iter_chunked(8192):
                    for event in parser.feed(chunk):
                        if not verified:
                            verified = True
                            connected()
                        yield event
                raise CameraError("Camera closed its alert stream")
        except ClientConnectorCertificateError as err:
            raise CameraCertificateError("Camera HTTPS certificate could not be verified") from err
        except (ClientError, TimeoutError) as err:
            raise CameraError("Camera alert stream interrupted") from err
