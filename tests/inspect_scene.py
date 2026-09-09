"""Integration assertions executed by Blender against a saved scene."""

import argparse
import json
import math
import sys
from pathlib import Path

import bpy

config=json.loads((Path(__file__).resolve().parents[1]/"configs/street_scene.json").read_text())
parser=argparse.ArgumentParser()
parser.add_argument("scene",type=Path)
parser.add_argument("--owner",default=config["run_id"])
args=parser.parse_args(sys.argv[sys.argv.index("--")+1:])
scene_path=args.scene
bpy.ops.wm.open_mainfile(filepath=str(scene_path))
scene=bpy.context.scene
assert scene.get("task_owner")==args.owner, "Wrong scene identity"
assert scene.render.engine=="CYCLES" and scene.cycles.device=="GPU"
assert (scene.render.resolution_x,scene.render.resolution_y)==(1920,1080)
assert (scene.frame_start,scene.frame_end,scene.render.fps)==(1,120,24)
assert not bpy.data.libraries, "Unexpected linked dependency"
assert not [i for i in bpy.data.images if i.source=="FILE" and not i.packed_file]
root=bpy.data.objects["Hero car path"]
camera=scene.camera
assert camera.name=="Chase camera path"
assert bpy.data.objects.get("Afternoon sun direction")
scene.frame_set(1)
start=root.location.copy()
start_camera=camera.location.copy()
scene.frame_set(120)
assert abs(root.location.y-start.y-17.5)<1e-5
assert (camera.location-start_camera-(root.location-start)).length<1e-5
scene.frame_set(61)
expected_y=2+17.5*60/119
assert abs(root.location.y-expected_y)<1e-5, "Motion is not linear"
for obj in scene.objects:
    assert all(math.isfinite(v) for v in obj.location), f"Invalid transform: {obj.name}"
    if obj.type=="MESH":
        assert len(obj.data.vertices)>0, f"Empty geometry: {obj.name}"
        assert len(obj.data.materials)>0, f"Missing material: {obj.name}"
print(json.dumps({"scene":str(scene_path),"objects":len(scene.objects),
                  "checks":"owner, Cycles GPU, size, fps, dependencies, linear car and camera motion, geometry"}))
