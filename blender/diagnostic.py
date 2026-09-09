"""Owned diagnostic geometry. Run only in a fresh background Blender process."""

import json
import math
import sys
import time
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline.runtime import check_capacity, heavy_lock
import datetime
import shutil

config = json.loads((ROOT / "configs/street_scene.json").read_text())
run = Path(config["data_root"]) / config["run_id"]
deadline = datetime.datetime.fromisoformat(config["deadline_utc"]).timestamp()


def material(name, color, roughness=0.5, metallic=0.0):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (*color, 1)
    mat.use_nodes = True
    node = mat.node_tree.nodes.get("Principled BSDF")
    node.inputs["Base Color"].default_value = (*color, 1)
    node.inputs["Roughness"].default_value = roughness
    node.inputs["Metallic"].default_value = metallic
    return mat


def box(name, location, dimensions, mat, bevel=0):
    bpy.ops.mesh.primitive_cube_add(size=1, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = dimensions
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.data.materials.append(mat)
    if bevel:
        mod = obj.modifiers.new("Edge radius", "BEVEL")
        mod.width = bevel
        mod.segments = 3
        obj.modifiers.new("Weighted normals", "WEIGHTED_NORMAL")
    return obj


def build():
    if not bpy.app.background:
        raise RuntimeError("Diagnostic requires a separate background process")
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    scene = bpy.context.scene
    scene.name = "StreetDiagnostic"
    scene["task_owner"] = config["run_id"]
    asphalt = material("Asphalt", (.045, .053, .07), .92)
    concrete = material("Sidewalk", (.32, .34, .37), .8)
    brick = material("Brick", (.33, .11, .067), .72)
    stone = material("Stone", (.42, .27, .17), .7)
    glass = material("Window glass", (.028, .042, .055), .23, .25)
    red = material("Red paint", (.5, .018, .008), .23, .55)
    rubber = material("Rubber", (.009, .012, .017), .8)
    box("Street", (0, 32, -.13), (12, 100, .25), asphalt)
    for side in [-1, 1]:
        box("Sidewalk", (side * 7, 32, 0), (2, 100, .25), concrete)
        for j in range(10):
            y = j * 8
            box("Facade", (side * 10.5, y, 10), (5, 7.9, 20), brick)
            for floor in range(5):
                z = 2 + floor * 3.5
                for bay in [-2.5, 0, 2.5]:
                    box("Window frame", (side * 7.96, y + bay, z),
                        (.14, 1.55, 2.4), stone)
                    box("Window", (side * 7.87, y + bay, z),
                        (.08, 1.25, 2.1), glass)
    box("Car body proxy", (0, 2, .7), (2.05, 4.7, .8), red, .24)
    box("Car cabin proxy", (0, 2.4, 1.25), (1.55, 2.2, .7), glass, .23)
    box("Rear grille proxy", (0, -.365, .62), (1.7, .05, .43), rubber, .08)
    for x in [-1.02, 1.02]:
        for y in [.4, 3.6]:
            bpy.ops.mesh.primitive_cylinder_add(vertices=40, radius=.37, depth=.25,
                                                location=(x, y, .4),
                                                rotation=(0, math.pi / 2, 0))
            bpy.context.object.name = "Wheel proxy"
            bpy.context.object.data.materials.append(rubber)
    bpy.ops.object.camera_add(location=(0, -7, 2.5))
    camera = bpy.context.object
    camera.name = "Chase camera"
    camera.rotation_euler = (Vector((0, 22, 1.7)) - camera.location).to_track_quat("-Z", "Y").to_euler()
    camera.data.lens = 35
    scene.camera = camera
    bpy.ops.object.light_add(type="SUN", location=(0, 0, 30))
    bpy.context.object.name = "Afternoon sun"
    bpy.context.object.rotation_euler = Vector((.7, .2, -1)).to_track_quat("-Z", "Y").to_euler()
    bpy.context.object.data.energy = 3
    bpy.context.object.data.angle = math.radians(1.3)
    scene.world.use_nodes = True
    scene.world.node_tree.nodes["Background"].inputs[0].default_value = (.23, .34, .5, 1)
    scene.world.node_tree.nodes["Background"].inputs[1].default_value = .45
    scene.render.engine = "CYCLES"
    prefs = bpy.context.preferences.addons["cycles"].preferences
    prefs.compute_device_type = "METAL"
    prefs.get_devices()
    for device in prefs.devices:
        device.use = device.type == "METAL"
    if not any(d.use and d.type == "METAL" for d in prefs.devices):
        raise RuntimeError("No Metal GPU is available")
    scene.cycles.device = "GPU"
    scene.cycles.samples = 24
    scene.cycles.use_denoising = True
    scene.cycles.seed = 42
    scene.render.resolution_x = 1920
    scene.render.resolution_y = 1080
    scene.render.resolution_percentage = 50
    scene.render.image_settings.file_format = "PNG"
    scene.render.fps = 24
    scene.frame_start = 1
    scene.frame_end = 120
    scene.view_settings.view_transform = "AgX"
    return scene


if __name__ == "__main__":
    run.mkdir(parents=True, exist_ok=True)
    check_capacity(now=time.time(), deadline=deadline, estimate_seconds=180,
                   reserve_seconds=300, free_bytes=shutil.disk_usage(run).free,
                   min_free_bytes=config["min_free_bytes"],
                   used_bytes=sum(p.stat().st_size for p in run.rglob("*") if p.is_file()),
                   max_bytes=config["max_additional_bytes"], estimate_bytes=100_000_000)
    with heavy_lock(Path(config["data_root"]) / "heavy.lock"):
        start = time.monotonic()
        scene = build()
        output = run / "diagnostic"
        output.mkdir(exist_ok=True)
        bpy.ops.wm.save_as_mainfile(filepath=str(output / "baseline.blend"))
        scene.render.filepath = str(output / "baseline.png")
        bpy.ops.render.render(write_still=True)
        (output / "baseline.json").write_text(json.dumps({
            "kind": "diagnostic, not production acceptance",
            "elapsed_seconds": time.monotonic() - start,
            "engine": scene.render.engine, "device": scene.cycles.device,
            "compute_type": "METAL", "samples": scene.cycles.samples,
            "resolution": [960, 540], "owner": scene["task_owner"]
        }, indent=2))
