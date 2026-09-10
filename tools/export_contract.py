"""Read-only preconditions for an isolated export of a frozen scene."""

import datetime
import re
from pathlib import Path

from pipeline.evidence import digest


def verify_source(path, expected_sha256):
    """Require an existing regular file with the exact approved SHA256."""
    if not isinstance(expected_sha256, str) or not re.fullmatch(
            r"[0-9a-f]{64}", expected_sha256):
        raise ValueError("Expected SHA256 must be 64 lowercase hexadecimal characters")
    source = Path(path).resolve(strict=True)
    if not source.is_file():
        raise ValueError("Source must be a regular file")
    if digest(source) != expected_sha256:
        raise ValueError("Source SHA256 differs from the approved frozen scene")


def sample_seconds(frame):
    """Map source frames 1..120 to 0..119/24, without stretching the motion."""
    if type(frame) is not int or not 1 <= frame <= 120:
        raise ValueError("Source frame must be an integer from 1 through 120")
    return (frame - 1) / 24


def _absolute_path(value):
    if not isinstance(value, (str, Path)):
        raise ValueError("Explicit absolute paths are required")
    path = Path(value)
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError("Paths must be absolute and must not contain parent traversal")
    return path.resolve()


def _overlap(first, second):
    return first.is_relative_to(second) or second.is_relative_to(first)


def verify_output_path(source, output, *, staging_root, readonly_roots):
    """Accept only a new/empty directory strictly inside disjoint owned staging.

    This read-only preflight is not a filesystem sandbox. The caller must keep
    staging exclusively task-owned and create fresh output before each export.
    """
    source = _absolute_path(source)
    output = _absolute_path(output)
    staging = _absolute_path(staging_root)
    if not isinstance(readonly_roots, (list, tuple)) or not readonly_roots:
        raise ValueError("Explicit read-only roots are required")
    protected = [_absolute_path(root) for root in readonly_roots]
    protected.append(source)
    if any(_overlap(staging, root) for root in protected):
        raise ValueError("Staging overlaps a read-only source boundary")
    if not staging.is_dir():
        raise ValueError("Task-owned staging must already be a directory")
    if output == staging or not output.is_relative_to(staging):
        raise ValueError("Output must be a strict descendant of task-owned staging")
    if any(_overlap(output, root) for root in protected):
        raise ValueError("Output overlaps a read-only source boundary")
    if output.exists():
        if source.exists() and output.samefile(source):
            raise ValueError("Output aliases the frozen source")
        if not output.is_dir():
            raise ValueError("Output must be a directory")
        if any(output.iterdir()):
            raise ValueError("Output must be new or empty; existing exports are not overwritten")
    return output


def _utc_timestamp(value, name):
    if not isinstance(value, str):
        raise ValueError(f"{name} must be an explicit timezone-aware timestamp")
    try:
        date = datetime.datetime.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"{name} must be an explicit timezone-aware timestamp") from error
    if date.utcoffset() is None:
        raise ValueError(f"{name} must be an explicit timezone-aware timestamp")
    return date.timestamp()


def validate_allowance(config, *, now=None):
    """Reject inactive, expired or unbounded resource settings before any work.

    Resource monitoring, locking and the five-minute reserve remain owned by
    pipeline.job; this validates the fresh allowance it will consume.
    """
    if not isinstance(config, dict) or config.get("enabled") is not True:
        raise ValueError("Export allowance is inactive; obtain fresh explicit authorization")
    for field in ("max_additional_bytes", "min_free_bytes"):
        value = config.get(field)
        if type(value) is not int or value <= 0:
            raise ValueError(f"{field} must be a positive finite integer byte count")
    if type(config.get("max_heavy_jobs")) is not int or config["max_heavy_jobs"] != 1:
        raise ValueError("Export permits exactly one heavy job at a time")
    started = _utc_timestamp(config.get("started_utc"), "started_utc")
    deadline = _utc_timestamp(config.get("deadline_utc"), "deadline_utc")
    if now is None:
        now = datetime.datetime.now(datetime.timezone.utc)
    if not isinstance(now, datetime.datetime) or now.utcoffset() is None:
        raise ValueError("Current time must be timezone-aware")
    current = now.timestamp()
    if started > current or deadline <= current + 300 or deadline <= started:
        raise ValueError("Export allowance is not current or consumes the five-minute reserve")


def validate_export_job(config, *, now=None):
    """Validate the supervisor's write boundary before it creates logs or locks."""
    validate_allowance(config, now=now)
    source = _absolute_path(config.get("source"))
    verify_source(source, config.get("source_sha256"))
    staging = _absolute_path(config.get("data_root"))
    roots = config.get("readonly_roots")
    if not isinstance(roots, list) or not roots:
        raise ValueError("Explicit read-only roots are required")
    protected = [_absolute_path(root) for root in roots] + [source]
    if not staging.is_dir() or any(_overlap(staging, root) for root in protected):
        raise ValueError("Supervisor staging overlaps a source boundary or does not exist")
    run_id = config.get("run_id")
    if not isinstance(run_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", run_id):
        raise ValueError("Run identifier must be a single safe directory name")
    run = (staging / run_id).resolve()
    if not run.is_relative_to(staging) or run == staging or any(_overlap(run, root) for root in protected):
        raise ValueError("Supervised run escapes owned staging")
    return run
