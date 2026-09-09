"""Assemble an owned editable street scene in a fresh Blender process."""

import argparse
import json
import math
import sys
import time
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "blender"))
from hero_car import build_car
from street import build_street
from parked_cars import build_parked
from pipeline.evidence import atomic_json, digest, fingerprint, retain_dependencies


def linear_animation(obj):
    action = obj.animation_data.action if obj.animation_data else None
    if action:
        for layer in action.layers:
            for strip in layer.strips:
                for bag in strip.channelbags:
                    for curve in bag.fcurves:
                        for key in curve.keyframe_points:
                            key.interpolation = "LINEAR"


def configure(scene):
    scene.render.engine = "CYCLES"
    prefs = bpy.context.preferences.addons["cycles"].preferences
    prefs.compute_device_type = "METAL"
    prefs.get_devices()
    for device in prefs.devices:
        device.use = device.type == "METAL"
    if not any(d.use and d.type == "METAL" for d in prefs.devices):
        raise RuntimeError("Metal GPU unavailable")
    scene.cycles.device = "GPU"
    scene.cycles.samples = 64
    scene.cycles.use_denoising = True
    scene.cycles.seed = 42
    scene.cycles.max_bounces = 6
    scene.render.resolution_x, scene.render.resolution_y = 1920, 1080
    scene.render.resolution_percentage = 100
    scene.render.fps = 24
    scene.frame_start, scene.frame_end = 1, 120
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.image_settings.color_depth = "8"
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.view_settings.exposure = .3
    scene.render.film_transparent = False


def assemble(config):
    if not bpy.app.background:
        raise RuntimeError("Assembly requires an isolated background process")
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    scene = bpy.context.scene
    scene.name = "Manhattan Rear Chase"
    scene["task_owner"] = config["run_id"]
    scene["source_frame_start"] = 150
    scene["source_frame_end_exclusive"] = 270
    scene["reference_target_matched"] = False
    scene["user_acceptance"] = "pending"
    scene.unit_settings.system = "METRIC"
    bpy.context.collection.name = "Street architecture"
    configure(scene)
    build_street(Path(config["data_root"])/config["run_id"]/"assets/bricks")
    car = build_car(name="Hero", paint_color=(.9,.06,.018), location=(.08,2,0))
    root = car["root"]
    root.name = "Hero car path"
    root["editing_help"] = "Edit Location keyframes on frames 1 and 120. Wheel rolling uses matching keyframes."
    travel = 17.5
    for frame, y in [(1,2),(120,2+travel)]:
        root.location.y = y
        root.keyframe_insert(data_path="location",frame=frame)
    linear_animation(root)
    for wheel in car["wheels"]:
        wheel.rotation_euler.x = 0
        wheel.keyframe_insert(data_path="rotation_euler",frame=1)
        wheel.rotation_euler.x = -travel / car["radius"]
        wheel.keyframe_insert(data_path="rotation_euler",frame=120)
        linear_animation(wheel)
    parked=[]
    for index, (x,y,color) in enumerate([
        (-4.2,8,(.23,.25,.29)),(-4.3,35,(.13,.15,.18)),
        (4.5,18,(.14,.16,.19)),(4.5,42,(.19,.22,.25)),
        (-4.3,62,(.06,.075,.09)),(4.5,68,(.13,.14,.15)),
    ]):
        parked.append(build_parked(f"Parked vehicle {index+1}",
                                  kind="minivan" if index in [0,3] else "sedan",
                                  location=(x,y,0),color=color))
    bpy.ops.object.camera_add(location=(-.6,-7.2,1.5))
    camera = bpy.context.object
    camera.name = "Chase camera path"
    camera.data.lens = 37
    camera.data.clip_end = 800
    camera.rotation_euler = Vector((1.35,20,-.88)).to_track_quat("-Z","Y").to_euler()
    camera["editing_help"] = "Edit Location keyframes and Lens. Rotation controls target elevation."
    for frame,y in [(1,-7.2),(120,-7.2+travel)]:
        camera.location.y=y
        camera.keyframe_insert(data_path="location",frame=frame)
    linear_animation(camera)
    scene.camera=camera
    bpy.ops.object.light_add(type="SUN",location=(0,0,30))
    sun=bpy.context.object
    sun.name="Afternoon sun direction"
    sun.rotation_euler=Vector((.7,.22,-1)).to_track_quat("-Z","Y").to_euler()
    sun.data.energy=6
    sun.data.color=(1.0,.88,.75)
    sun.data.angle=math.radians(.8)
    sun["editing_help"]="Rotate to change shadow direction. Energy changes direct sunlight."
    scene.world.use_nodes=True
    background=scene.world.node_tree.nodes["Background"]
    sky=scene.world.node_tree.nodes.new("ShaderNodeTexSky")
    sky.sky_type="MULTIPLE_SCATTERING"
    sky.sun_disc=False
    sky.sun_elevation=math.atan2(1,math.hypot(.7,.22))
    sky.sun_rotation=math.atan2(-.22,-.7)
    sky.altitude=.1
    sky.air_density=1
    sky.aerosol_density=.1
    scene.world.node_tree.links.new(sky.outputs[0],background.inputs[0])
    background.inputs[1].default_value=.12
    # Separate visible sky exposure from the HDR illumination used by surfaces.
    visible_sky=scene.world.node_tree.nodes.new("ShaderNodeBackground")
    visible_sky.name="Visible sky exposure"
    visible_sky.inputs[0].default_value=(.26,.42,.64,1)
    visible_sky.inputs[1].default_value=.8
    visibility=scene.world.node_tree.nodes.new("ShaderNodeLightPath")
    sky_mix=scene.world.node_tree.nodes.new("ShaderNodeMixShader")
    scene.world.node_tree.links.new(visibility.outputs["Is Camera Ray"],sky_mix.inputs[0])
    scene.world.node_tree.links.new(background.outputs[0],sky_mix.inputs[1])
    scene.world.node_tree.links.new(visible_sky.outputs[0],sky_mix.inputs[2])
    scene.world.node_tree.links.new(sky_mix.outputs[0],scene.world.node_tree.nodes["World Output"].inputs["Surface"])
    for name,objects in [
        ("Hero vehicle",[root]+list(root.children_recursive)),
        ("Parked traffic",[obj for vehicle in parked for obj in [vehicle]+list(vehicle.children_recursive)]),
        ("Camera and lighting",[camera,sun]),
    ]:
        collection=bpy.data.collections.new(name)
        scene.collection.children.link(collection)
        for obj in objects:
            for old in list(obj.users_collection):
                old.objects.unlink(obj)
            collection.objects.link(obj)
    scene.frame_set(1)
    return scene


if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--attempt",required=True)
    args=parser.parse_args(sys.argv[sys.argv.index("--")+1:])
    if not args.attempt.replace("-","").isalnum():
        raise ValueError("Invalid attempt name")
    config=json.loads((ROOT/"configs/street_scene.json").read_text())
    run=Path(config["data_root"])/config["run_id"]
    output=run/args.attempt
    output.mkdir(exist_ok=False)
    start=time.monotonic()
    scene=assemble(config)
    scene_path=output/"scene.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(scene_path))
    dependencies=[ROOT/"blender"/name for name in ["build_scene.py","street.py","hero_car.py","parked_cars.py"]]
    dependencies.append(ROOT/"configs/street_scene.json")
    for asset in ["bricks","asphalt"]:
        dependencies.extend((run/"assets"/asset).glob("*.jpg"))
        dependencies.append(run/"assets"/asset/"provenance.json")
    settings={"engine":"CYCLES","device":"METAL","samples":64,"size":[1920,1080],
              "seed":42,"fps":24,"frame_start":1,"frame_end":120}
    atomic_json(output/"scene.json",{
        "scene":str(scene_path),"sha256":digest(scene_path),
        "construction_fingerprint":fingerprint(dependencies,settings),
        "build_seconds":time.monotonic()-start,"settings":settings,
        "objects":len(scene.objects),"vertices":sum(len(o.data.vertices) for o in scene.objects if o.type=="MESH"),
        "dependencies":{str(p):digest(p) for p in dependencies},
        "retained_dependencies":retain_dependencies(dependencies,output/"dependencies"),
        "user_acceptance":"pending","quality":"unreviewed"
    })
    scene.render.resolution_percentage=50
    scene.cycles.samples=24
    scene.render.filepath=str(output/"preview.png")
    render_start=time.monotonic()
    bpy.ops.render.render(write_still=True)
    atomic_json(output/"preview.json",{
        "seconds":time.monotonic()-render_start,"sha256":digest(output/"preview.png"),
        "frame":1,"samples":24,"resolution":[960,540],"kind":"preview only"
    })
