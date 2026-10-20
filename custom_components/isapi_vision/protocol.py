"""Bounded, namespace-independent ISAPI parsing; no Home Assistant imports."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from xml.etree.ElementTree import Element, ParseError, TreeBuilder, XMLParser, fromstring

from .const import EVENT_MAP, PERSISTENT_ALARMS

MAX_XML = 1024 * 1024
MAX_PARAMETERS = 3000
MAX_XML_DEPTH = 64
MAX_XML_NODES = 20000
START = re.compile(rb"<(?:[A-Za-z_][\w.-]*:)?EventNotificationAlert\b")
END = re.compile(rb"</(?:[A-Za-z_][\w.-]*:)?EventNotificationAlert\s*>")
SENSITIVE = (
    "password",
    "passwd",
    "secret",
    "token",
    "credential",
    "authorization",
    "privatekey",
    "community",
    "username",
    "serialnumber",
    "macaddress",
    "ipaddress",
    "ipv6address",
    "gateway",
    "dns",
    "hostname",
    "devicename",
    "email",
    "certificate",
    "security",
    "url",
    "uri",
    "address",
    "passphrase",
    "authkey",
    "apikey",
    "encryptionkey",
)


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


class CameraTreeBuilder(TreeBuilder):
    """Reject all DTDs at the parser callback, regardless of input encoding."""

    def __init__(self) -> None:
        super().__init__()
        self.depth = 0
        self.nodes = 0

    def doctype(self, name, pubid, system) -> None:
        raise ValueError("Camera XML must not contain a DTD")

    def start(self, tag, attrs):
        self.depth += 1
        self.nodes += 1
        if self.depth > MAX_XML_DEPTH or self.nodes > MAX_XML_NODES:
            raise ValueError("Camera XML exceeds structural limits")
        return super().start(tag, attrs)

    def end(self, tag):
        self.depth -= 1
        return super().end(tag)


def parse_xml(payload: bytes) -> Element:
    if len(payload) > MAX_XML:
        raise ValueError("XML response exceeds size limit")
    try:
        return fromstring(payload, parser=XMLParser(target=CameraTreeBuilder()))
    except ParseError as err:
        raise ValueError("Invalid camera XML") from err


def text(root: Element, key: str) -> str | None:
    return next(
        (node.text.strip() for node in root.iter() if local_name(node.tag) == key and node.text and node.text.strip()),
        None,
    )


def sensitive(name: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]", "", name.lower())
    return normalized in {"key", "psk", "login", "user", "userid", "ssid", "snmp"} or any(
        word in normalized for word in SENSITIVE
    )


def flatten(root: Element, secrets: tuple[str, ...] = ()) -> dict[str, str]:
    """Export non-sensitive scalar leaves and XML capability attributes."""
    result: dict[str, str] = {}

    def safe(value: str) -> str:
        return "[redacted]" if any(secret and secret in value for secret in secrets) else value

    def walk(node: Element, path: str, depth: int = 0) -> None:
        if depth > 32 or len(result) >= MAX_PARAMETERS or sensitive(local_name(node.tag)):
            return
        for key, value in node.attrib.items():
            if not sensitive(local_name(key)) and len(result) < MAX_PARAMETERS:
                result[safe(f"{path}/@{local_name(key)}")] = safe(value)[:255]
        if not len(node):
            value = (node.text or "").strip()
            if value and len(result) < MAX_PARAMETERS:
                result[safe(path)] = safe(value) if len(value) <= 255 else "[value exceeds HA state limit]"
            return
        counts = Counter(local_name(child.tag) for child in node)
        positions: Counter[str] = Counter()
        for child in node:
            name = local_name(child.tag)
            positions[name] += 1
            suffix = ""
            if counts[name] > 1:
                identity = next(((item.text or "").strip() for item in child if local_name(item.tag) == "id"), "")
                safe_id = re.sub(r"[^A-Za-z0-9_.-]", "_", identity)
                suffix = f"[id={safe_id}]" if safe_id else f"[{positions[name]}]"
            walk(child, f"{path}/{name}{suffix}", depth + 1)

    walk(root, local_name(root.tag))
    return result


@dataclass(frozen=True)
class CameraEvent:
    event_type: str
    state: str
    channel: str | None
    targets: frozenset[str]
    rule: str


def parse_event(root: Element) -> CameraEvent:
    targets = set()
    # Some firmware uses a direct targetType; others nest detectionTarget under a region.
    for node in root.iter():
        if local_name(node.tag).lower() in {"targettype", "detectiontarget", "targetclassification"}:
            for value in re.split(r"[,;\s]+", (node.text or "").lower()):
                if value in {"human", "person"}:
                    targets.add("person")
                elif value in {"vehicle", "car", "truck", "bus", "motorcycle"}:
                    targets.add("vehicle")
    return CameraEvent(
        (text(root, "eventType") or "unknown").lower(),
        (text(root, "eventState") or "unknown").lower(),
        text(root, "channelID") or text(root, "dynChannelID"),
        frozenset(targets),
        text(root, "ruleID") or text(root, "regionID") or "",
    )


class AlertParser:
    """Extract XML across arbitrary chunks, discarding MIME headers and image parts."""

    def __init__(self) -> None:
        self.buffer = b""

    def feed(self, chunk: bytes) -> list[CameraEvent]:
        self.buffer += chunk
        events = []
        while True:
            start = START.search(self.buffer)
            if not start:
                self.buffer = self.buffer[-128:]
                return events
            self.buffer = self.buffer[start.start() :]
            end = END.search(self.buffer)
            if not end:
                if len(self.buffer) > MAX_XML:
                    self.buffer = self.buffer[-128:]
                return events
            document, self.buffer = self.buffer[: end.end()], self.buffer[end.end() :]
            try:
                root = parse_xml(document)
                if local_name(root.tag) == "EventNotificationAlert":
                    events.append(parse_event(root))
            except ValueError:
                continue


class AlarmState:
    """Aggregate active rules without clearing a second detector's active alarm."""

    def __init__(self, channel: int, hold: int, debounce: int = 0) -> None:
        self.channel = str(channel)
        self.hold = hold
        self.debounce = debounce
        self.active: dict[tuple[str, str, str], float] = {}
        self.pending_off: dict[tuple[str, str, str], float] = {}
        self.seen: set[str] = set()
        self.last_event: str | None = None
        self.last_targets: tuple[str, ...] = ()

    def apply(self, event: CameraEvent, now: float) -> bool:
        if event.channel not in {None, self.channel}:
            return False
        if (
            event.event_type in {"videoloss", "heartbeat"}
            and event.state == "inactive"
            and not self.is_on("video_loss")
        ):
            # Hikvision uses inactive videoloss as a keepalive; don't label it a new alarm.
            return False
        if event.state not in {"active", "inactive"}:
            return False
        mapped = EVENT_MAP.get(event.event_type)
        self.last_event = event.event_type
        self.last_targets = tuple(sorted(event.targets))
        keys = (
            set(event.targets)
            if mapped in {"motion", "line_crossing", "intrusion", "region_entrance", "region_exit"}
            else set()
        )
        if mapped:
            keys.add(mapped)
        self.seen.update(keys)
        if event.state == "active":
            for key in keys:
                self.active[(key, event.event_type, event.rule)] = (
                    float("inf") if key in PERSISTENT_ALARMS or not self.hold else now + self.hold
                )
                self.pending_off.pop((key, event.event_type, event.rule), None)
        else:
            # An inactive notification often omits targetType or ruleID entirely.
            for source in list(self.active):
                key, event_type, rule = source
                if event_type == event.event_type and (not event.rule or rule == event.rule):
                    if not event.targets or key in keys:
                        del self.active[source]
                        if self.debounce:
                            self.pending_off[source] = now + self.debounce
            # A target-specific OFF must not clear motion while the other target is active.
            if mapped and event.targets:
                remaining = [
                    deadline
                    for (key, kind, rule), deadline in self.active.items()
                    if key in {"person", "vehicle"} and kind == event.event_type and rule == event.rule
                ]
                if remaining:
                    self.active[(mapped, event.event_type, event.rule)] = max(remaining)
                    self.pending_off.pop((mapped, event.event_type, event.rule), None)
        return True

    def expire(self, now: float) -> bool:
        expired = [source for source, deadline in self.active.items() if deadline <= now]
        for source in expired:
            ended = self.active.pop(source)
            if self.debounce:
                self.pending_off[source] = ended + self.debounce
        cleared = [source for source, deadline in self.pending_off.items() if deadline <= now]
        for source in cleared:
            del self.pending_off[source]
        return bool(expired or cleared)

    def is_on(self, key: str) -> bool:
        return any(source[0] == key for source in self.active) or any(source[0] == key for source in self.pending_off)

    def clear(self) -> None:
        self.active.clear()
        self.pending_off.clear()
