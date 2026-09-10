"""Export a frozen scene in an isolated, supervised Blender process."""

import argparse
import json
import math
import re
import shutil
import struct
import sys
import time
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "blender"))
from gltf_materials import prepare_materials
from pipeline.evidence import atomic_json, digest
from tools.export_contract import sample_seconds, validate_export_job, verify_output_path, verify_source


ROLE_NAMES = {
    "Chase camera path": "ChaseCamera",
    "Hero car path": "HeroCar",
    "Hero.FrontL.Hub": "WheelFL", "Hero.FrontR.Hub": "WheelFR",
    "Hero.RearL.Hub": "WheelRL", "Hero.RearR.Hub": "WheelRR",
    "Afternoon sun direction": "Sun",
}


def read_glb(path):
    data = Path(path).read_bytes()
    if struct.unpack_from("<III", data) != (0x46546C67, 2, len(data)):
        raise ValueError("Invalid exported GLB header")
    length, kind = struct.unpack_from("<II", data, 12)
    if kind != 0x4E4F534A:
        raise ValueError("Missing exported GLB JSON")
    return json.loads(data[20:20 + length]), data[20 + length:]


def write_glb(path, document, binary_chunk):
    encoded = json.dumps(document, separators=(",", ":"), sort_keys=True).encode()
    encoded += b" " * (-len(encoded) % 4)
    Path(path).write_bytes(struct.pack("<III", 0x46546C67, 2, 20 + len(encoded) + len(binary_chunk))
                          + struct.pack("<II", len(encoded), 0x4E4F534A) + encoded + binary_chunk)


def source_snapshot(scene):
    graph = bpy.context.evaluated_depsgraph_get()
    camera = scene.camera
    projection = camera.calc_matrix_camera(graph, x=1920, y=1080)
    poses = []
    for frame in range(1, 121):
        scene.frame_set(frame)
        controls = {}
        for old, role in ROLE_NAMES.items():
            if role == "Sun":
                continue
            obj = scene.objects.get(old)
            if obj is None:
                raise ValueError(f"Missing source role: {role}")
            controls[role] = {
                "matrix": [value for row in obj.matrix_world for value in row],
                "rotationX": obj.rotation_euler.x,
            }
        poses.append({"frame": frame, "seconds": sample_seconds(frame), "controls": controls})
    scene.frame_set(1)
    inventory = []
    for obj in scene.objects:
        if obj.type not in {"MESH", "FONT"}:
            continue
        evaluated = obj.evaluated_get(graph)
        mesh = evaluated.to_mesh()
        mesh.calc_loop_triangles()
        inventory.append({
            "sourceName": obj.name, "type": obj.type,
            "triangles": len(mesh.loop_triangles),
            "vertices": len(mesh.vertices),
            "materials": [slot.material.name for slot in obj.material_slots],
            "bounds": [list(obj.matrix_world @ Vector(corner)) for corner in obj.bound_box],
        })
        evaluated.to_mesh_clear()
    return {
        "camera": {"aspect": 16 / 9, "yfov": 2 * math.atan(1 / projection[1][1]),
                   "near": camera.data.clip_start, "far": camera.data.clip_end,
                   "projection": [projection[row][column] for column in range(4) for row in range(4)]},
        "poses": poses, "inventory": inventory,
    }


def export(source, output, config):
    started = time.monotonic()
    if not bpy.app.background:
        raise RuntimeError("Export requires an isolated background process")
    run = validate_export_job(config)
    if Path(source).resolve() != Path(config["source"]).resolve():
        raise ValueError("CLI source differs from authorized source")
    output = verify_output_path(source, output, staging_root=run,
                                readonly_roots=config["readonly_roots"])
    output.mkdir(exist_ok=True)
    bpy.ops.wm.open_mainfile(filepath=str(source), use_scripts=False)
    scene = bpy.context.scene
    if (scene.frame_start, scene.frame_end, scene.render.fps) != (1, 120, 24):
        raise ValueError("Unexpected source sample interval")
    source_record = json.loads((Path(source).parent / "scene.json").read_text())
    if source_record["sha256"] != config["source_sha256"]:
        raise ValueError("Retained source manifest has a different scene identity")
    texture_hashes = {Path(path).name: checksum for path, checksum in source_record["dependencies"].items()
                      if path.endswith(".jpg")}
    snapshot = source_snapshot(scene)
    source_names = [obj.name for obj in scene.objects]
    texspaces = {obj.name: (obj.data.texspace_location.copy(), obj.data.texspace_size.copy())
                 for obj in scene.objects if obj.type == "MESH"}
    bpy.ops.object.select_all(action="DESELECT")
    for obj in scene.objects:
        if obj.type in {"MESH", "FONT"}:
            obj.select_set(True)
            bpy.context.view_layer.objects.active = obj
    bpy.ops.object.convert(target="MESH")
    if sorted(obj.name for obj in scene.objects) != sorted(source_names):
        raise ValueError("Evaluated geometry conversion changed the object inventory")
    for name, (location, size) in texspaces.items():
        mesh = scene.objects[name].data
        mesh.use_auto_texspace = False
        mesh.texspace_location = location
        mesh.texspace_size = size
    material_record = prepare_materials(scene, output / "textures", config["recipe"], texture_hashes)
    logical_names = {}
    for obj in sorted(scene.objects, key=lambda obj: obj.name):
        name = obj.name
        stable = ROLE_NAMES.get(name, re.sub(r"[^A-Za-z0-9_-]", "_", name))
        obj.name = stable
        if obj.name != stable or stable in logical_names.values():
            raise ValueError("Exported object names are not unique")
        logical_names[name] = stable
        if obj.data:
            obj.data.name = stable
    scene.name = "StreetSequence"
    scene.frame_set(1)
    raw = output / "attempt-23.raw.glb"
    bpy.ops.export_scene.gltf(
        filepath=str(raw), export_format="GLB", export_yup=True, export_apply=False,
        export_cameras=True, export_lights=True, export_extras=False,
        export_animations=True, export_animation_mode="SCENE",
        export_anim_scene_split_object=False, export_frame_range=True, export_frame_step=1,
        export_force_sampling=True, export_anim_slide_to_zero=True,
        export_optimize_animation_size=False, export_bake_animation=False,
        export_morph=False, export_skins=False, export_tangents=True,
        export_image_format="AUTO", will_save_settings=False)
    document, binary = read_glb(raw)
    if len(document.get("animations", [])) != 1:
        raise ValueError("Expected exactly one exported scene clip")
    document["animations"][0]["name"] = "StreetSequence"
    cameras = document.get("cameras", [])
    if len(cameras) != 1 or abs(cameras[0]["perspective"]["yfov"] - snapshot["camera"]["yfov"]) > 1e-5:
        raise ValueError("Exporter camera projection differs from the effective source projection")
    write_glb(raw, document, binary)
    checksum = digest(raw)
    public_file = f"attempt-23.{checksum}.glb"
    shutil.copyfile(raw, output / public_file)
    triangles = sum(document["accessors"][primitive["indices"]]["count"] // 3
                    for mesh in document["meshes"] for primitive in mesh["primitives"])
    if triangles != sum(item["triangles"] for item in snapshot["inventory"]):
        raise ValueError("Exported triangle inventory differs from evaluated source")
    sun = scene.objects["Sun"]
    direction = sun.matrix_world.to_quaternion() @ Vector((0, 0, -1))
    manifest = {
        "schemaVersion": 1, "design": "attempt-23", "sourceSceneSha256": config["source_sha256"],
        "asset": {"file": public_file, "sha256": checksum, "bytes": raw.stat().st_size},
        "animation": {"clip": "StreetSequence", "fps": 24, "frameStart": 1, "frameEnd": 120,
                      "motionEndSeconds": 119 / 24, "durationSeconds": 5},
        "roles": {"camera": "ChaseCamera", "hero": "HeroCar", "sun": "Sun",
                  "wheels": {"frontLeft": "WheelFL", "frontRight": "WheelFR",
                             "rearLeft": "WheelRL", "rearRight": "WheelRR"}},
        "expected": {"camera": snapshot["camera"], "samples": 120, "travelMeters": 17.5,
                     "wheelRadians": -17.5 / 0.36},
        "lighting": {
            "sunDirection": [direction.x, direction.z, -direction.y],
            "sunIntensity": 6, "environmentIntensity": 0.7,
            "skyColor": [0.5, 0.65, 0.9], "groundColor": [0.12, 0.1, 0.08],
            "background": [0.208, 0.336, 0.512], "exposure": 2 ** 0.3,
            "shadow": {"mapSize": 2048, "mobileMapSize": 1024,
                       "bounds": [-28, 28, -40, 40, 0.1, 150],
                       "bias": -0.0001, "normalBias": 0.025}},
        "materials": material_record["materials"],
        "statistics": {
            "triangles": triangles, "materials": len(document["materials"]),
            "images": len(document["images"]), "logicalObjects": len(snapshot["inventory"]),
            "textObjects": sum(item["type"] == "FONT" for item in snapshot["inventory"]),
            "geometryBytes": sum(view["byteLength"] for view in document["bufferViews"]
                                 if view.get("target") in {34962, 34963}),
            "textureBytes": sum(document["bufferViews"][image["bufferView"]]["byteLength"]
                                for image in document["images"])},
        "limits": {"sceneBytes": 30 * 1024 ** 2, "bundleGzipBytes": 1024 ** 2,
                   "triangles": 1100000, "drawCalls": 300, "desktopDpr": 1.5, "mobileDpr": 1},
    }
    atomic_json(output / "scene-manifest.json", manifest)
    verify_source(source, config["source_sha256"])
    atomic_json(output / "export-receipt.json", {
        "complete": True, "sourceBeforeSha256": config["source_sha256"],
        "sourceAfterSha256": digest(source), "glbSha256": checksum,
        "seconds": time.monotonic() - started, "blender": bpy.app.version_string,
        "source": snapshot, "logicalNames": logical_names, "conversion": material_record,
    })
    print("GLTF_EXPORT_COMPLETE", checksum, triangles, raw.stat().st_size)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--recipe", required=True, type=Path)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
    config = json.loads(args.recipe.read_text())
    try:
        export(args.source, args.output, config)
    finally:
        verify_source(args.source, config["source_sha256"])
