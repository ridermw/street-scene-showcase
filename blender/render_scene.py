"""Reopen an immutable checkpoint and capture selected frames with evidence."""

import argparse
import datetime
import json
import shutil
import sys
import time
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT/"blender"))
from pipeline.capture import capture_owner, delivery_gate, forecast, validate_capture
from pipeline.evidence import atomic_json, digest, fingerprint
from pipeline.runtime import check_capacity

parser = argparse.ArgumentParser()
parser.add_argument("--attempt", required=True)
parser.add_argument("--mode", choices=["anchors","motion","full"], default="anchors")
args = parser.parse_args(sys.argv[sys.argv.index("--")+1:])
if not args.attempt.replace("-","").isalnum():
    raise ValueError("Invalid attempt name")
config = json.loads((ROOT/"configs/street_scene.json").read_text())
run = Path(config["data_root"])/config["run_id"]
attempt = run/args.attempt
scene_path = attempt/"scene.blend"
record = json.loads((attempt/"scene.json").read_text())
if digest(scene_path) != record["sha256"]:
    raise ValueError("Scene changed after checkpoint recording")
if not bpy.app.background:
    raise RuntimeError("Capture requires isolated background process")
bpy.ops.wm.open_mainfile(filepath=str(scene_path))
scene = bpy.context.scene
prefs = bpy.context.preferences.addons["cycles"].preferences
prefs.compute_device_type="METAL"
prefs.get_devices()
for device in prefs.devices:
    device.use=device.type=="METAL"
if not any(d.use and d.type=="METAL" for d in prefs.devices):
    raise RuntimeError("Metal GPU unavailable")
validate_capture({"owner":capture_owner(config,record["sha256"]),"engine":"CYCLES","device":"GPU","backend":"METAL"},
                 {"owner":scene.get("task_owner"),"engine":scene.render.engine,
                  "device":scene.cycles.device,"backend":prefs.compute_device_type})
if any(image.source=="FILE" and not image.packed_file for image in bpy.data.images):
    raise ValueError("Unpacked image dependency; retain and fingerprint it before capture")
scene.render.resolution_percentage = 50 if args.mode=="motion" else 100
scene.cycles.samples = 24 if args.mode=="motion" else 64
settings = dict(record["settings"], resolution_percentage=scene.render.resolution_percentage,
                samples=scene.cycles.samples)
identity = fingerprint([scene_path],settings)
reference_identity = config["reference"]["sha256"]
if args.mode=="full":
    approval=json.loads((attempt/"approval.json").read_text())
    deadline=datetime.datetime.fromisoformat(config["deadline_utc"]).timestamp()-300
    used=sum(p.stat().st_size for p in run.rglob("*") if p.is_file())
    delivery_gate(approval,identity,reference_identity,deadline-time.time(),
                  min(shutil.disk_usage(run).free-config["min_free_bytes"],
                      config["max_additional_bytes"]-used))
frames = [1,61,120] if args.mode=="anchors" else list(range(1,13 if args.mode=="motion" else 121))
output = attempt/args.mode
output.mkdir(exist_ok=True)
records=[]
for frame in frames:
    if (run/"PAUSE").exists():
        raise RuntimeError("Capture paused; completed frames remain available")
    deadline=datetime.datetime.fromisoformat(config["deadline_utc"]).timestamp()
    check_capacity(now=time.time(),deadline=deadline,estimate_seconds=60,
                   reserve_seconds=300,free_bytes=shutil.disk_usage(run).free,
                   min_free_bytes=config["min_free_bytes"],
                   used_bytes=sum(p.stat().st_size for p in run.rglob("*") if p.is_file()),
                   max_bytes=config["max_additional_bytes"],estimate_bytes=20_000_000)
    path=output/f"{frame:04d}.png"
    metadata=path.with_suffix(".json")
    if path.exists() and metadata.exists():
        previous=json.loads(metadata.read_text())
        if previous["fingerprint"]!=identity or previous["sha256"]!=digest(path):
            raise ValueError("Cannot resume a stale or mixed frame sequence")
        records.append(previous)
        continue
    if path.exists() or metadata.exists():
        raise ValueError("Incomplete frame evidence; preserve and inspect before retry")
    scene.frame_set(frame)
    scene.render.filepath=str(path)
    start=time.monotonic()
    bpy.ops.render.render(write_still=True)
    row={"frame":frame,"fingerprint":identity,"sha256":digest(path),
         "seconds":time.monotonic()-start,"bytes":path.stat().st_size,"path":str(path)}
    atomic_json(metadata,row)
    records.append(row)
atomic_json(output/"sequence.json",records)
if args.mode=="anchors":
    projection=forecast(120,[r["seconds"] for r in records],[r["bytes"] for r in records],
                        60,120,.25,scene_path.stat().st_size)
    projection.update({"fingerprint":identity,"reference_fingerprint":reference_identity,
                       "device":"METAL","decision":"unreviewed"})
    atomic_json(attempt/"forecast.json",projection)
