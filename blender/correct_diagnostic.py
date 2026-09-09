"""Apply the image critic's camera correction to the retained diagnostic."""

import hashlib
import json
import sys
import time
from pathlib import Path

import bpy
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
from diagnostic import config, run, deadline, check_capacity, heavy_lock
import shutil

if not bpy.app.background:
    raise RuntimeError("Use a separate background Blender process")
output = run / "diagnostic"
check_capacity(now=time.time(), deadline=deadline, estimate_seconds=300,
               reserve_seconds=300, free_bytes=shutil.disk_usage(run).free,
               min_free_bytes=config["min_free_bytes"], used_bytes=0,
               max_bytes=config["max_additional_bytes"], estimate_bytes=100_000_000)
with heavy_lock(Path(config["data_root"]) / "heavy.lock"):
    bpy.ops.wm.open_mainfile(filepath=str(output / "baseline.blend"))
    scene = bpy.context.scene
    if scene.get("task_owner") != config["run_id"]:
        raise RuntimeError("Wrong scene owner")
    camera = scene.camera
    camera.location = (0, -8, 2.5)
    camera.rotation_euler = (Vector((0, 13, 0)) - camera.location).to_track_quat("-Z", "Y").to_euler()
    scene.render.filepath = str(output / "corrected.png")
    bpy.ops.wm.save_as_mainfile(filepath=str(output / "corrected.blend"))
    timings = []
    for name, reopen, percent, samples in [
        ("corrected", False, 50, 24),
        ("repeat", False, 50, 24),
        ("reopened", True, 50, 24),
        ("final-spec", False, 100, 64),
    ]:
        start = time.monotonic()
        if reopen:
            bpy.ops.wm.open_mainfile(filepath=str(output / "corrected.blend"))
            scene = bpy.context.scene
        scene.render.resolution_percentage = percent
        scene.cycles.samples = samples
        scene.render.filepath = str(output / f"{name}.png")
        bpy.ops.render.render(write_still=True)
        timings.append({"name": name, "seconds": time.monotonic() - start,
                        "resolution_percentage": percent, "samples": samples,
                        "bytes": (output / f"{name}.png").stat().st_size,
                        "sha256": hashlib.sha256((output / f"{name}.png").read_bytes()).hexdigest()})
    (output / "cycle.json").write_text(json.dumps({
        "kind": "diagnostic only",
        "correction": "Moved camera back one meter and aimed lower, following independent framing critique.",
        "timings": timings,
        "provisional_sequence_seconds": timings[-1]["seconds"] * 120 * 1.25 + 120,
        "provisional_sequence_bytes": timings[-1]["bytes"] * 120 * 2,
        "note": "Diagnostic forecast is not a production forecast. Repeat hashes measure this device only."
    }, indent=2))
