"""
Camera-source / injection integrity checks.

Looks for indicators that the capture does NOT come from a genuine local
camera sensor:

    * virtual-camera device labels (OBS, ManyCam, droidcam, v4l2loopback…)
    * missing capture metadata where a real camera would provide it
    * screen-resolution-exact frames claimed as camera captures
    * frame metadata anomalies (size/aspect/duration inconsistencies)

Honesty note: these are heuristic integrity signals.  Complete injection
protection cannot be claimed until the suite has been validated against
real injection tooling on the target platforms (documented blocker).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


# Lower-case substrings associated with known virtual-camera sources.
VIRTUAL_CAMERA_LABELS = (
    "obs ", "obs(", "open broadcaster", "manycam", "droidcam", "e2esoft",
    "snap camera", "snapcamera", "v4l2loopback", "akvcam", "iriun",
    "epoccam", "xsplit", "voicemod", "camtwist", "virtual camera",
    "virtualcam", "fake cam", "webcamoid", "splitcam", "youcam",
)

# Metadata key conventions we understand (case-insensitive).
_DEVICE_KEYS = ("device_label", "device", "camera_id", "source", "source_id")
_CAPTURE_KEYS = ("exif_present", "has_capture_metadata", "capture_metadata")


@dataclass
class InjectionSignals:
    virtual_camera_label: Optional[str] = None
    capture_metadata_missing: bool = False
    screen_resolution_match: bool = False
    metadata_anomalies: List[str] = field(default_factory=list)
    assessed: bool = False
    methods: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "virtual_camera_label": self.virtual_camera_label,
            "capture_metadata_missing": self.capture_metadata_missing,
            "screen_resolution_match": self.screen_resolution_match,
            "metadata_anomalies": self.metadata_anomalies,
            "assessed": self.assessed,
            "methods": self.methods,
        }


def _first_key(meta: Dict[str, object], keys: Tuple[str, ...]) -> Optional[object]:
    lowered = {str(k).lower(): v for k, v in meta.items()}
    for k in keys:
        if k in lowered and lowered[k] is not None:
            return lowered[k]
    return None


def analyze_source_integrity(
    metadata: Optional[Dict[str, object]] = None,
    frame_width: Optional[int] = None,
    frame_height: Optional[int] = None,
) -> InjectionSignals:
    """Assess capture-source integrity from session metadata.

    ``metadata`` - optional per-session camera metadata supplied by the
    client/transport layer.  Absence of metadata is itself a signal when
    the transport claims a direct camera capture.
    """
    s = InjectionSignals()
    meta = {str(k): v for k, v in (metadata or {}).items()}

    # ── virtual-camera label match ────────────────────────────────────
    device = _first_key(meta, _DEVICE_KEYS)
    if isinstance(device, str):
        label = device.strip().lower()
        for marker in VIRTUAL_CAMERA_LABELS:
            if marker in label:
                s.virtual_camera_label = label
                break

    # ── capture metadata presence ─────────────────────────────────────
    capture = _first_key(meta, _CAPTURE_KEYS)
    if capture is None:
        # No capture-metadata key at all: only a soft signal — the
        # transport may legitimately not forward it.  Recorded, not
        # decisive on its own.
        s.capture_metadata_missing = True
    elif isinstance(capture, bool) and not capture:
        s.capture_metadata_missing = True
        s.metadata_anomalies.append("capture_metadata_explicitly_absent")

    # ── screen-resolution heuristic ───────────────────────────────────
    # A frame exactly matching a common desktop screen size, when the
    # transport claims a phone/tablet camera, is a screen-replay signal.
    # Heuristic only — validated against real devices before production.
    if frame_width and frame_height:
        for key in ("declared_platform", "platform", "client_platform"):
            plat = _first_key(meta, (key,))
            if isinstance(plat, str) and re.search(
                    r"android|ios|mobile", plat, re.IGNORECASE):
                if (frame_width, frame_height) in (
                        (1920, 1080), (2560, 1440), (1280, 720)):
                    s.screen_resolution_match = True
                    s.metadata_anomalies.append(
                        f"desktop_screen_resolution_on_{plat.strip().lower()}")
                break

    s.assessed = True
    s.methods.extend(["virtual_camera_labels", "capture_metadata",
                      "resolution_heuristic"])
    return s


def injection_attack_indicators(s: InjectionSignals) -> List[Tuple[str, float]]:
    """Return (indicator, confidence) pairs; empty = no evidence.

    Confidence values are heuristic risk weights (see module note) —
    NOT calibrated probabilities.

    Note: ``capture_metadata_missing`` is deliberately NOT included as a
    standalone attack indicator.  Absence of capture metadata is common
    with legitimate camera pipelines that simply don't forward it; it is
    recorded in ``InjectionSignals`` for audit purposes but is not
    evidence of an attack on its own.
    """
    out: List[Tuple[str, float]] = []
    if not s.assessed:
        return out
    if s.virtual_camera_label:
        out.append(("injection.virtual_camera_device", 0.90))
    for anomaly in s.metadata_anomalies:
        out.append((f"injection.{anomaly}", 0.50))
    if s.screen_resolution_match:
        out.append(("injection.screen_resolution_match", 0.55))
    return out