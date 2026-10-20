"""Evidence-based discovery from camera replies, with no firmware/model heuristics."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, replace
from xml.etree.ElementTree import Element

from .const import DETECTIONS, EVENT_MAP, SMART_PATH_NAMES
from .protocol import local_name


def normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def tokens(value: str) -> set[str]:
    return {normalize(part) for part in re.split(r"[,;\s]+", value) if part}


def boolean(value: str | None) -> bool | None:
    if value is not None:
        if value.strip().lower() in {"true", "1"}:
            return True
        if value.strip().lower() in {"false", "0"}:
            return False
    return None


def scoped_nodes(root: Element, channel: int):
    """Ignore capability records explicitly belonging to another video channel."""

    def walk(node):
        ids = [child.text for child in node if normalize(local_name(child.tag)) in {"channelid", "videoinputchannelid"}]
        if "channel" in normalize(local_name(node.tag)) or normalize(local_name(node.tag)) in {
            "linedetection",
            "fielddetection",
            "regionentrance",
            "regionexiting",
        }:
            ids += [child.text for child in node if normalize(local_name(child.tag)) == "id"]
        if any(value and value.strip() != str(channel) for value in ids):
            return
        yield node
        for child in node:
            yield from walk(child)

    return walk(root)


FLAGS = {
    "motion": {"issupportmotiondetection", "issupportvmd"},
    "person": {"issupporthumandetection", "issupportpersondetection", "issupporthuman"},
    "vehicle": {"issupportvehicledetection", "issupportvehicle"},
    "line_crossing": {"issupportlinedetection", "issupportlinecrossing"},
    "intrusion": {"issupportfielddetection", "issupportintrusion"},
    "region_entrance": {"issupportregionentrance"},
    "region_exit": {"issupportregionexiting"},
    "tamper": {"issupporttamperdetection", "issupportshelteralarm"},
    "video_loss": {"issupportvideoloss"},
    "disk_error": {"issupporthderror", "issupportdiskerror"},
    "disk_full": {"issupporthdfull", "issupportdiskfull"},
    "alarm_input": {"issupportalarmin", "issupportalarminput"},
}
FLAG_FEATURES = {flag: feature for feature, flags in FLAGS.items() for flag in flags}
EVENT_FEATURES = {normalize(event): feature for event, feature in EVENT_MAP.items()}
CONFIG_ROOTS = {
    "motion": {"motiondetection"},
    "tamper": {"tamperdetection"},
    **{feature: {normalize(name), normalize(name) + "list"} for feature, name in SMART_PATH_NAMES.items()},
}
TARGET_TAGS = {"targettype", "detectiontarget", "targetclassification"}
CAPABILITY_KEYS = {"capabilities", "event_capabilities", "channel_event_capabilities", "smart_capabilities"}


@dataclass(frozen=True)
class FeatureInfo:
    support: str = "unknown"
    enabled: bool | None = None
    evidence: tuple[str, ...] = ()

    def observed(self) -> FeatureInfo:
        return replace(self, support="supported", evidence=tuple(sorted(set(self.evidence) | {"event_stream"})))


def feature_report(features: dict[str, FeatureInfo]) -> dict[str, dict]:
    return {key: asdict(value) for key, value in sorted(features.items())}


def valid_feature_document(key: str, root: Element) -> bool:
    """HTTP 200 with an unrelated XML document is not feature support."""
    feature = key.removesuffix("_capabilities")
    if feature not in CONFIG_ROOTS:
        return True
    roots = CONFIG_ROOTS[feature]
    if key.endswith("_capabilities"):
        roots = roots | {name + suffix for name in roots for suffix in ("cap", "capabilities")}
    return normalize(local_name(root.tag)) in roots


def discover_features(
    documents: dict[str, Element], channel: int, probes: dict[str, dict[str, str]] | None = None
) -> dict[str, FeatureInfo]:
    """Absence, HTTP failures and missing paths remain unknown, not unsupported."""
    positive: dict[str, set[str]] = {key: set() for key in DETECTIONS}
    negative: dict[str, set[str]] = {key: set() for key in DETECTIONS}
    attempts: dict[str, set[str]] = {key: set() for key in DETECTIONS}
    enabled: dict[str, bool | None] = {key: None for key in DETECTIONS}
    target_config: dict[str, list[bool | None]] = {"person": [], "vehicle": []}
    for source, paths in (probes or {}).items():
        feature = source.removesuffix("_capabilities")
        if feature in CONFIG_ROOTS:
            for path, status in paths.items():
                attempts[feature].add(f"{path}:{status}")

    for source, root in documents.items():
        nodes = list(scoped_nodes(root, channel))
        if not nodes or normalize(local_name(root.tag)) == "html":
            continue
        is_capability = source in CAPABILITY_KEYS or source.endswith("_capabilities")
        if is_capability:
            for node in nodes:
                name = normalize(local_name(node.tag))
                if (feature := FLAG_FEATURES.get(name)) and (value := boolean(node.text)) is not None:
                    (positive if value else negative)[feature].add(
                        f"{source}:{local_name(node.tag)}={str(value).lower()}"
                    )
                if name in {"eventtype", "supporteventtype", "supportedeventtypes"}:
                    declared = tokens(node.text or "") | tokens(node.attrib.get("opt", ""))
                    for event in declared:
                        if feature := EVENT_FEATURES.get(event):
                            positive[feature].add(f"{source}:eventType={event}")

        feature = source.removesuffix("_capabilities")
        if feature in CONFIG_ROOTS and valid_feature_document(source, root):
            if normalize(local_name(root.tag)).endswith("list") and not any(
                normalize(local_name(node.tag)) in CONFIG_ROOTS[feature]
                and not normalize(local_name(node.tag)).endswith("list")
                for node in nodes
            ):
                continue
            explicitly_unsupported = is_capability and any(
                (
                    normalize(local_name(node.tag)) in {"issupport", "supported"}
                    or FLAG_FEATURES.get(normalize(local_name(node.tag))) == feature
                )
                and boolean(node.text) is False
                for node in root
            )
            if explicitly_unsupported:
                negative[feature].add(f"{source}:isSupport=false")
                continue
            positive[feature].add(f"{source}:readable_api")
            if not is_capability:
                enabled[feature] = next(
                    (boolean(child.text) for child in root if normalize(local_name(child.tag)) == "enabled"), None
                )
            for node in nodes:
                if normalize(local_name(node.tag)) in TARGET_TAGS:
                    declared = tokens(node.text or "") | tokens(node.attrib.get("opt", ""))
                    current = tokens(node.text or "")
                    for target, aliases in (("person", {"human", "person"}), ("vehicle", {"vehicle", "car"})):
                        if declared & aliases:
                            positive[target].add(f"{source}:targetType={target}")
                        if not is_capability and (node.text or "").strip():
                            target_config[target].append(
                                False if not current & aliases or enabled[feature] is False else enabled[feature]
                            )
        if source == "alarm_inputs" and any(
            normalize(local_name(node.tag)) in {"ioport", "inputport", "ioinputport"} for node in nodes
        ):
            positive["alarm_input"].add("alarm_inputs:input_present")

    for target, values in target_config.items():
        enabled[target] = (
            True if True in values else False if values and all(value is False for value in values) else None
        )
    return {
        key: FeatureInfo(
            "supported" if positive[key] else "unsupported" if negative[key] else "unknown",
            enabled[key],
            tuple(sorted(positive[key] | negative[key] | attempts[key])),
        )
        for key in DETECTIONS
    }
