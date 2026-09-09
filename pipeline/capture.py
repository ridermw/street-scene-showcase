"""Capture identity and full sequence capacity gates."""

import math


def capture_owner(config, scene_sha256):
    locked=config.get("locked_scene_sha256")
    if locked is not None and locked!=scene_sha256:
        raise ValueError("Scene differs from the approved frozen design")
    if "scene_owner" in config:
        owner=config["scene_owner"]
        if locked is None or not isinstance(owner,str) or not owner.strip():
            raise ValueError("Imported scene requires a locked hash and original owner")
        return owner
    return config["run_id"]


def validate_capture(expected, actual):
    for key in ("owner", "engine", "device", "backend"):
        if expected[key] != actual[key]:
            raise ValueError(f"Capture {key} differs from declared specification")


def forecast(count, seconds, sizes, preparation, encoding, retry_fraction, retained_bytes):
    if (not seconds or len(seconds) != len(sizes) or count < 1
            or any(not math.isfinite(t) or t <= 0 for t in seconds)
            or any(s <= 0 for s in sizes)):
        raise ValueError("Forecast requires positive representative frame measurements")
    return {
        "seconds": count * max(seconds) * (1 + retry_fraction) + preparation + encoding,
        "bytes": count * max(sizes) * 2 + retained_bytes,
        "sample_count": len(seconds), "frame_count": count,
        "seconds_range": [min(seconds), max(seconds)],
        "retry_fraction": retry_fraction, "preparation_seconds": preparation,
        "encoding_seconds": encoding, "retained_bytes": retained_bytes,
    }


def delivery_gate(approval, current_fingerprint, reference_fingerprint,
                  remaining_seconds, available_bytes):
    if (approval["fingerprint"] != current_fingerprint
            or approval["reference_fingerprint"] != reference_fingerprint
            or approval["decision"] != "accept"):
        raise ValueError("Delivery lacks current design acceptance")
    if (not math.isfinite(remaining_seconds) or remaining_seconds <= 0
            or not math.isfinite(available_bytes) or available_bytes <= 0
            or not math.isfinite(approval["seconds"]) or approval["seconds"] <= 0
            or approval["seconds"] > remaining_seconds
            or not math.isfinite(approval["bytes"])
            or approval["bytes"] <= 0 or approval["bytes"] > available_bytes):
        raise ValueError("Delivery exceeds remaining capacity")
