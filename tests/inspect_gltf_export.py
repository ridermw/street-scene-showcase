"""Run separately in supervised Blender; never part of ordinary discovery."""

import argparse
import json
import math
import re
import struct
import sys
from pathlib import Path

import bpy
from mathutils import Matrix, Quaternion, Vector

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "blender"))
from pipeline.evidence import atomic_json, digest


def material_fixture():
    from gltf_materials import signed_planar_uv, normal_pixels
    import numpy as np

    point = (2.0, 3.0, 5.0)
    for normal, expected in [
        ((1, 0, 0), (1.5, 2.5)), ((-1, 0, 0), (-0.5, 2.5)),
        ((0, 1, 0), (0.0, 2.5)), ((0, -1, 0), (1.0, 2.5)),
        ((0, 0, 1), (-0.5, 1.0)), ((0, 0, -1), (1.5, 1.0)),
    ]:
        assert signed_planar_uv(point, normal, 2) == expected
    try:
        signed_planar_uv(point, (0.707, 0.707, 0), 2)
    except ValueError:
        pass
    else:
        raise AssertionError("Non-axis-aligned box projection was silently approximated")
    flat = normal_pixels(np.full((4, 4), 0.5), 1.05, 0.028, 0.38)
    assert np.allclose(flat[:, :, :3], [0.5, 0.5, 1])
    slope = np.tile(np.arange(8) / 8, (8, 1))
    result = normal_pixels(slope, 1, 0.1, 0.5)
    assert result[3, 3, 0] < 0.5 and result[3, 3, 1] == 0.5
    assert np.isfinite(result).all()
    vertical = normal_pixels(slope.T, 1, 0.1, 0.5)
    assert vertical[3, 3, 1] < 0.5 and vertical[3, 3, 0] == 0.5
    inverted = normal_pixels(1 - slope, 1, 0.1, 0.5)
    assert inverted[3, 3, 0] > 0.5
    shifted = normal_pixels(np.roll(slope, 3, axis=1), 1, 0.1, 0.5)
    assert np.allclose(shifted, np.roll(result, 3, axis=1)), "Normals introduce a nonperiodic tile seam"
    return {"fixture": "signed-planar-and-normal", "complete": True}


def semantic_checks(scene, name=lambda value: value):
    graph = bpy.context.evaluated_depsgraph_get()
    for origin, direction, axis, wall, sign in [
        ((-17.3, 91, 5), (0, 1, 0), 1, 93, 1),
        ((7.2, 114, 5), (0, 1, 0), 1, 116, 1),
        ((4, 118, 5), (1, 0, 0), 0, 6, 1),
        ((-3.5, 95, 5), (-1, 0, 0), 0, -5.5, -1),
    ]:
        hit, point, normal, index, obj, matrix = scene.ray_cast(
            graph, Vector(origin), Vector(direction), distance=4)
        assert hit and obj.name == name("Middle distance windows"), "Recessed glazing is missing"
        assert sign * (point[axis] - wall) > 0.05, "Glazing projects in front of masonry"
    trim = scene.objects[name("Sandstone lintels and cornices")]
    for sign, wall in [(1, 8.0), (-1, 8.15)]:
        for bottom, top in [(3.8, 4.2), (6.6, 7.0)]:
            points = [v.co for v in trim.data.vertices
                      if 7.4 < sign * v.co.x < 8.5 and abs(v.co.y - 6) < 0.84 and bottom < v.co.z < top]
            assert points and max(sign * p.x for p in points) >= wall + 0.015, "Detached trim"
            if bottom == 3.8:
                assert max(p.z for p in points) >= 4.1, "Unsupported sill"
    surfaces = [obj for obj in scene.objects if obj.name == name("Hero.Continuous sculpted upper body")
                or "shoulder" in obj.name and "vent" in obj.name]

    def top_at(x, y):
        heights = []
        for obj in surfaces:
            hit, point, normal, index = obj.ray_cast(Vector((x, y, 2)), Vector((0, 0, -1)))
            if hit:
                heights.append(point.z)
        assert heights, "Shoulder surface is missing"
        return max(heights)

    for x in [-0.8, 0.8]:
        for y in [-1.89 + i * 0.113 for i in range(7)]:
            assert (top_at(x, y - 0.043) + top_at(x, y + 0.043)) / 2 - top_at(x, y) > 0.007, "Raised shoulder vent"


def material_crops(source, glb, output):
    import numpy as np
    from gltf_materials import signed_planar_uv

    output.mkdir(exist_ok=False)
    original_hash = digest(source)
    bpy.ops.wm.open_mainfile(filepath=str(source), use_scripts=False)
    scene = bpy.context.scene
    scene.frame_set(1)
    original = {name: bpy.data.materials[name] for name in ["Brick 0", "Fine asphalt", "Hero.Satin carbon"]}
    for material in original.values():
        material.use_fake_user = True
    aerofoil = scene.objects["Hero.Thin red rear aerofoil"]
    source_wing = bpy.data.meshes.new_from_object(aerofoil.evaluated_get(bpy.context.evaluated_depsgraph_get()))
    source_wing.use_fake_user = True
    source_wing.use_auto_texspace = False
    source_wing.texspace_location = aerofoil.data.texspace_location
    source_wing.texspace_size = aerofoil.data.texspace_size
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    before = set(bpy.data.materials)
    bpy.ops.import_scene.gltf(filepath=str(glb))
    converted = {}
    for material in set(bpy.data.materials) - before:
        for name in original:
            if material.name == name or material.name.startswith(name + "."):
                converted[name] = material
                material.use_fake_user = True
    converted_wing = bpy.data.objects["Hero_Thin_red_rear_aerofoil"].data.copy()
    converted_wing.use_fake_user = True
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    scene.world = bpy.data.worlds.new("FixtureWorld")
    scene.world.use_nodes = True
    scene.world.node_tree.nodes["Background"].inputs[0].default_value = (0.15, 0.15, 0.15, 1)
    scene.world.node_tree.nodes["Background"].inputs[1].default_value = 1
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 16
    scene.cycles.use_denoising = False
    scene.cycles.seed = 42
    scene.render.threads_mode = "FIXED"
    scene.render.threads = 4
    scene.render.resolution_x = scene.render.resolution_y = 256
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "None"
    scene.view_settings.exposure = 0
    camera_data = bpy.data.cameras.new("FixtureCamera")
    camera_data.type = "ORTHO"
    camera_data.ortho_scale = 1
    camera = bpy.data.objects.new("FixtureCamera", camera_data)
    scene.collection.objects.link(camera)
    scene.camera = camera
    light_data = bpy.data.lights.new("FixtureSun", "SUN")
    light_data.energy = 2
    light = bpy.data.objects.new("FixtureSun", light_data)
    scene.collection.objects.link(light)
    pattern = bpy.data.images.new("asymmetric-fixture", width=64, height=64, alpha=False)
    y, x = np.mgrid[0:64, 0:64]
    rgba = np.ones((64, 64, 4), dtype=np.float32)
    rgba[:, :, 0] = x / 63
    rgba[:, :, 1] = y / 63
    rgba[:, :, 2] = ((x // 9 + y // 13) % 2) * 0.7
    pattern.pixels.foreach_set(rgba.ravel())
    pattern.pack()
    records = []

    def render_case(label, source_mat, converted_mat, normal, *, emission=False, asymmetric=False):
        normal = Vector(normal)
        u = normal.cross(Vector((0, 0, 1)) if abs(normal.z) < 0.9 else Vector((0, 1, 0))).normalized()
        v = normal.cross(u)
        center = Vector((2.15, 3.3, 5.7))
        points = [center + u * a + v * b for a, b in [(-0.45, -0.45), (0.45, -0.45),
                                                     (0.45, 0.45), (-0.45, 0.45)]]
        camera.location = center + normal * 4
        camera.rotation_euler = (-normal).to_track_quat("-Z", "Y").to_euler()
        light.rotation_euler = (-normal + u * 0.8 + v * 0.2).to_track_quat("-Z", "Y").to_euler()
        for kind, material in [("source", source_mat), ("converted", converted_mat)]:
            mesh = bpy.data.meshes.new("FixturePlane")
            mesh.from_pydata(points, [], [(0, 1, 2, 3)])
            obj = bpy.data.objects.new("FixturePlane", mesh)
            scene.collection.objects.link(obj)
            material = material.copy()
            if asymmetric:
                for node in material.node_tree.nodes:
                    if node.type == "TEX_IMAGE" and node.image and "Color" in node.image.name:
                        node.image = pattern
            if kind == "converted":
                uv = mesh.uv_layers.new(name="UVMap")
                meters = 1.5 if "asphalt" in label else 1.05
                for index in range(4):
                    uv.data[index].uv = signed_planar_uv(points[index], normal, meters)
            if emission:
                nodes, links = material.node_tree.nodes, material.node_tree.links
                bsdf = next(node for node in nodes if node.type == "BSDF_PRINCIPLED")
                output_node = next(node for node in nodes if node.type == "OUTPUT_MATERIAL")
                emit = nodes.new("ShaderNodeEmission")
                color = bsdf.inputs["Base Color"]
                if color.is_linked:
                    links.new(color.links[0].from_socket, emit.inputs[0])
                else:
                    emit.inputs[0].default_value = color.default_value
                links.new(emit.outputs[0], output_node.inputs["Surface"])
            mesh.materials.append(material)
            path = output / f"{label}-{kind}.png"
            scene.render.filepath = str(path)
            bpy.ops.render.render(write_still=True)
            records.append({"file": path.name, "sha256": digest(path)})
            bpy.data.objects.remove(obj, do_unlink=True)
    for index, normal in enumerate([(1, 0, 0), (-1, 0, 0), (0, 1, 0),
                                    (0, -1, 0), (0, 0, 1), (0, 0, -1)]):
        render_case(f"axis-{index}", original["Brick 0"], converted["Brick 0"], normal,
                    emission=True, asymmetric=True)
    for label, name in [("brick-normal", "Brick 0"), ("asphalt-normal", "Fine asphalt")]:
        render_case(label, original[name], converted[name], (0, 0, 1))
    camera.location = (0, -2.6, 0.45)
    camera.rotation_euler = (Vector((0, -1.87, 1.138)) - camera.location).to_track_quat("-Z", "Y").to_euler()
    camera.data.ortho_scale = 0.35
    light.rotation_euler = (0.3, 0.4, 0)
    for kind, mesh in [("source", source_wing), ("converted", converted_wing)]:
        mesh = mesh.copy()
        for index, material in enumerate(mesh.materials):
            material = material.copy()
            mesh.materials[index] = material
            nodes, links = material.node_tree.nodes, material.node_tree.links
            shader = next(node for node in nodes if node.type == "BSDF_PRINCIPLED")
            output_node = next(node for node in nodes if node.type == "OUTPUT_MATERIAL")
            emit = nodes.new("ShaderNodeEmission")
            color = shader.inputs["Base Color"]
            if color.is_linked:
                links.new(color.links[0].from_socket, emit.inputs[0])
            else:
                emit.inputs[0].default_value = color.default_value
            links.new(emit.outputs[0], output_node.inputs["Surface"])
        obj = bpy.data.objects.new("FixtureWing", mesh)
        scene.collection.objects.link(obj)
        path = output / f"carbon-paint-{kind}.png"
        scene.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        records.append({"file": path.name, "sha256": digest(path)})
        bpy.data.objects.remove(obj, do_unlink=True)
    assert digest(source) == original_hash
    return {"complete": True, "sourceSha256": original_hash, "glbSha256": digest(glb),
            "records": records, "visualApproval": None, "fixtureSize": [256, 256]}


def actual_export(source, glb):
    import numpy as np

    source_hash = digest(source)
    bpy.ops.wm.open_mainfile(filepath=str(source), use_scripts=False)
    scene = bpy.context.scene
    scene.frame_set(1)
    semantic_checks(scene)
    graph = bpy.context.evaluated_depsgraph_get()
    payload = Path(glb).read_bytes()
    length = struct.unpack_from("<I", payload, 12)[0]
    document = json.loads(payload[20:20 + length])
    binary = payload[28 + length:]
    types = {5121: np.uint8, 5123: np.uint16, 5125: np.uint32, 5126: np.float32}
    dimensions = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}

    def accessor(index):
        item = document["accessors"][index]
        view = document["bufferViews"][item["bufferView"]]
        dtype = np.dtype(types[item["componentType"]])
        count = dimensions[item["type"]]
        return np.ndarray((item["count"], count), dtype=dtype, buffer=binary,
                          offset=view.get("byteOffset", 0) + item.get("byteOffset", 0),
                          strides=(view.get("byteStride", dtype.itemsize * count), dtype.itemsize)).copy()

    names = {
        "Chase camera path": "ChaseCamera", "Hero car path": "HeroCar",
        "Hero.FrontL.Hub": "WheelFL", "Hero.FrontR.Hub": "WheelFR",
        "Hero.RearL.Hub": "WheelRL", "Hero.RearR.Hub": "WheelRR",
        "Afternoon sun direction": "Sun",
    }
    stable = lambda name: names.get(name, re.sub(r"[^A-Za-z0-9_-]", "_", name))
    nodes = document["nodes"]
    node_by_name = {node["name"]: index for index, node in enumerate(nodes)}
    assert len(node_by_name) == len(nodes), "Duplicate exported nodes"
    assert set(node_by_name) == {stable(obj.name) for obj in scene.objects}, "Node inventory changed"
    material_by_name = {material["name"]: material for material in document["materials"]}
    source_materials = {slot.material for obj in scene.objects for slot in obj.material_slots}
    assert len(material_by_name) == len(document["materials"])
    assert set(material_by_name) == {material.name for material in source_materials}, "Material inventory changed"
    for material in source_materials:
        shader = material.node_tree.nodes.get("Principled BSDF")
        actual = material_by_name[material.name]
        pbr = actual.get("pbrMetallicRoughness", {})
        assert abs(pbr.get("metallicFactor", 1) - shader.inputs["Metallic"].default_value) < 1e-6
        roughness = shader.inputs["Roughness"]
        if roughness.is_linked:
            assert "metallicRoughnessTexture" in pbr
        else:
            assert abs(pbr.get("roughnessFactor", 1) - roughness.default_value) < 1e-6
        coat = actual.get("extensions", {}).get("KHR_materials_clearcoat", {})
        assert abs(coat.get("clearcoatFactor", 0) - shader.inputs["Coat Weight"].default_value) < 1e-6
        base = shader.inputs["Base Color"]
        if not base.is_linked:
            assert np.max(np.abs(np.array(pbr.get("baseColorFactor", [1, 1, 1, 1])) - base.default_value)) < 1e-6
        else:
            upstream = base.links[0].from_node
            assert "baseColorTexture" in pbr, f"Missing portable color texture: {material.name}"
            if upstream.type == "MIX_RGB":
                assert np.max(np.abs(np.array(pbr.get("baseColorFactor", [1, 1, 1, 1]))
                                     - upstream.inputs[2].default_value)) < 1e-6, f"Lost tint: {material.name}"
    parents = {child: index for index, node in enumerate(nodes) for child in node.get("children", [])}
    basis = Matrix(((1, 0, 0, 0), (0, 0, -1, 0), (0, 1, 0, 0), (0, 0, 0, 1)))

    def transform(index, overrides=None):
        node = nodes[index]
        if "matrix" in node:
            values = node["matrix"]
            local = Matrix([values[i::4] for i in range(4)])
        else:
            values = node | (overrides or {}).get(index, {})
            q = values.get("rotation", [0, 0, 0, 1])
            local = Matrix.LocRotScale(Vector(values.get("translation", [0, 0, 0])),
                                      Quaternion((q[3], *q[:3])),
                                      Vector(values.get("scale", [1, 1, 1])))
        return transform(parents[index], overrides) @ local if index in parents else local

    def canonical(positions, normals):
        rounded = np.round(positions, 4)
        order = np.lexsort((rounded[:, :, 2], rounded[:, :, 1], rounded[:, :, 0]), axis=1)
        positions = np.take_along_axis(positions, order[:, :, None], axis=1).reshape(-1, 9)
        normals = np.take_along_axis(normals, order[:, :, None], axis=1).reshape(-1, 9)
        keys = np.round(positions, 4)
        rows = np.lexsort(tuple(keys[:, column] for column in reversed(range(9))))
        return positions[rows], normals[rows]

    def compare(name, source_positions, source_normals, positions, normals):
        assert source_positions.shape == positions.shape, f"Triangle inventory changed: {name}"
        expected_p, expected_n = canonical(source_positions, source_normals)
        actual_p, actual_n = canonical(positions, normals)
        delta = np.abs(expected_p - actual_p)
        assert np.max(delta) <= 1e-4, f"Geometry changed: {name}, max delta {np.max(delta)}"
        assert np.max(np.abs(expected_n - actual_n)) <= 1e-4, f"Normals changed: {name}"

    total = 0
    texts = 0
    geometry_objects = [obj for obj in scene.objects if obj.type in {"MESH", "FONT"}]
    assert len(geometry_objects) == sum("mesh" in node for node in nodes), "Geometry additions or omissions"
    for obj in geometry_objects:
        evaluated = obj.evaluated_get(graph)
        mesh = evaluated.to_mesh()
        mesh.calc_loop_triangles()
        node_index = node_by_name[stable(obj.name)]
        actual_matrix = np.array(basis @ transform(node_index), dtype=np.float32)
        source_matrix = np.array(obj.matrix_world, dtype=np.float32)
        source_normal_matrix = np.linalg.inv(source_matrix[:3, :3]).T
        actual_normal_matrix = np.linalg.inv(actual_matrix[:3, :3]).T
        primitives = document["meshes"][nodes[node_index]["mesh"]]["primitives"]
        expected_by_material = {}
        for triangle in mesh.loop_triangles:
            mat = obj.material_slots[triangle.material_index].material.name
            expected_by_material.setdefault(mat, []).append(triangle)
        actual_by_material = {}
        for primitive in primitives:
            mat = document["materials"][primitive["material"]]["name"]
            assert mat not in actual_by_material, f"Unexpected duplicate material primitive: {obj.name}"
            actual_by_material[mat] = primitive
        assert set(expected_by_material) == set(actual_by_material), f"Material assignment changed: {obj.name}"
        for mat, triangles in expected_by_material.items():
            primitive = actual_by_material[mat]
            indices = accessor(primitive["indices"]).reshape(-1)
            positions = accessor(primitive["attributes"]["POSITION"])
            normals = accessor(primitive["attributes"]["NORMAL"])
            positions = (positions @ actual_matrix[:3, :3].T + actual_matrix[:3, 3])[indices].reshape(-1, 3, 3)
            normals = (normals @ actual_normal_matrix.T)[indices].reshape(-1, 3, 3)
            normals /= np.linalg.norm(normals, axis=2, keepdims=True)
            source_positions = np.array([[mesh.vertices[i].co[:] for i in t.vertices] for t in triangles],
                                        dtype=np.float32)
            source_positions = source_positions @ source_matrix[:3, :3].T + source_matrix[:3, 3]
            source_normals = np.array([[mesh.corner_normals[i].vector[:] for i in t.loops] for t in triangles],
                                     dtype=np.float32) @ source_normal_matrix.T
            source_normals /= np.linalg.norm(source_normals, axis=2, keepdims=True)
            compare(obj.name, source_positions, source_normals, positions, normals)
            total += len(triangles)
        texts += obj.type == "FONT"
        evaluated.to_mesh_clear()
    assert texts == 7 and total <= 1100000
    print("FULL_GEOMETRY_INVENTORY_MATCH", len(geometry_objects), total)
    assert len(document["animations"]) == 1
    clip = document["animations"][0]
    assert clip["name"] == "StreetSequence"
    animated = [obj for obj in scene.objects if obj.animation_data and obj.animation_data.action]
    assert len(animated) == 6 and len(clip["channels"]) == 6
    assert {nodes[c["target"]["node"]]["name"] for c in clip["channels"]} == {stable(o.name) for o in animated}
    channels = []
    for channel in clip["channels"]:
        sampler = clip["samplers"][channel["sampler"]]
        times = accessor(sampler["input"]).reshape(-1)
        assert len(times) == 120 and np.max(np.abs(times - np.arange(120) / 24)) < 1e-6
        channels.append((channel["target"], accessor(sampler["output"])))
    accumulated = {name: 0.0 for name in ["WheelFL", "WheelFR", "WheelRL", "WheelRR"]}
    previous = {}
    for frame in range(1, 121):
        scene.frame_set(frame)
        overrides = {}
        for target, values in channels:
            overrides.setdefault(target["node"], {})[target["path"]] = values[frame - 1].tolist()
            role = nodes[target["node"]]["name"]
            if role in accumulated:
                q = values[frame - 1]
                rotation = Quaternion((q[3], *q[:3])).normalized()
                if role in previous:
                    delta = previous[role].inverted() @ rotation
                    if delta.w < 0:
                        delta.negate()
                    accumulated[role] += 2 * math.atan2(delta.x, delta.w)
                previous[role] = rotation
        for obj in animated:
            role = stable(obj.name)
            matrix = basis @ transform(node_by_name[role], overrides)
            if obj.type != "CAMERA":
                matrix = matrix @ basis.inverted()
            expected = obj.matrix_world
            assert (matrix.translation - expected.translation).length <= 1e-4, f"Pose position {role}/{frame}"
            q, other = matrix.to_quaternion(), expected.to_quaternion()
            angle = 2 * math.acos(min(1, abs(q.normalized().dot(other.normalized()))))
            assert angle <= 1e-4, f"Pose rotation {role}/{frame}: {angle}"
    for role, angle in accumulated.items():
        assert abs(angle + 17.5 / 0.36) < 1e-4, f"Lost signed wheel revolutions: {role}"
    assert abs(scene.objects["Hero.FrontL.Hub"].rotation_euler.x + 17.5 / 0.36) < 1e-5
    camera = document["cameras"][0]["perspective"]
    effective = scene.camera.calc_matrix_camera(graph, x=1920, y=1080)
    assert abs(camera["yfov"] - 2 * math.atan(1 / effective[1][1])) <= 1e-5
    assert abs(camera["znear"] - scene.camera.data.clip_start) <= 1e-5
    assert abs(camera["zfar"] - scene.camera.data.clip_end) <= 1e-5
    assert digest(source) == source_hash
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(glb))
    bpy.context.scene.frame_set(0)
    bpy.context.view_layer.update()
    semantic_checks(bpy.context.scene, stable)
    assert digest(source) == source_hash
    return {"complete": True, "sourceSha256": source_hash, "glbSha256": digest(glb),
            "logicalObjects": len(geometry_objects), "triangles": total, "textObjects": texts,
            "poseSamples": 120, "signedWheelRadians": accumulated}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", action="store_true")
    parser.add_argument("--material-crops", type=Path)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--glb", type=Path)
    parser.add_argument("--receipt", required=True)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
    assert bpy.app.background
    if args.fixture:
        result = material_fixture()
    elif args.material_crops and args.source and args.glb:
        result = material_crops(args.source, args.glb, args.material_crops)
    elif args.source and args.glb:
        result = actual_export(args.source, args.glb)
    else:
        raise ValueError("Select a fixture or source and GLB inspection")
    atomic_json(args.receipt, result)
    print("GLTF_INSPECTION_COMPLETE")
