"""Exercise editing controls on a separate copy and reopen the edited scene."""

import argparse
import hashlib
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
source=args.scene.resolve()
original=hashlib.sha256(source.read_bytes()).hexdigest()
output=source.parent/"editing-demonstration"
bpy.ops.wm.open_mainfile(filepath=str(source))
scene=bpy.context.scene
assert scene.get("task_owner")==args.owner, "Wrong scene identity"
output.mkdir(exist_ok=False)
scene.frame_set(1)
car=bpy.data.objects["Hero car path"]
camera=scene.camera
sun=bpy.data.objects["Afternoon sun direction"]
car.location.x+=.4
car.keyframe_insert(data_path="location",frame=1)
camera.location.x+=.25
camera.keyframe_insert(data_path="location",frame=1)
camera.data.lens+=2
sun.data.energy*=1.1
expected={"car_x":car.location.x,"camera_x":camera.location.x,
          "lens":camera.data.lens,"sun":sun.data.energy}
copy=output/"editable-copy.blend"
bpy.ops.wm.save_as_mainfile(filepath=str(copy))
bpy.ops.wm.open_mainfile(filepath=str(copy))
scene=bpy.context.scene
scene.frame_set(1)
actual={"car_x":bpy.data.objects["Hero car path"].location.x,
        "camera_x":scene.camera.location.x,"lens":scene.camera.data.lens,
        "sun":bpy.data.objects["Afternoon sun direction"].data.energy}
assert all(math.isclose(actual[key],value,rel_tol=0,abs_tol=1e-6)
           for key,value in expected.items()), (actual,expected)
assert hashlib.sha256(source.read_bytes()).hexdigest()==original
prefs=bpy.context.preferences.addons["cycles"].preferences
prefs.compute_device_type="METAL"
prefs.get_devices()
for d in prefs.devices:
    d.use=d.type=="METAL"
assert any(d.use and d.type=="METAL" for d in prefs.devices)
scene.render.resolution_percentage=50
scene.cycles.samples=24
scene.render.filepath=str(output/"edited.png")
bpy.ops.render.render(write_still=True)
(output/"result.json").write_text(json.dumps({
    "source_unchanged_sha256":original,"reopened_controls":actual,
    "expected_controls":expected,"absolute_tolerance":1e-6,
    "editing_copy":str(copy),"render":str(output/"edited.png")
},indent=2))
print("Editing copy saved, reopened and rendered; source checkpoint unchanged")
