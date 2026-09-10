"""Explicit portable material conversion for the frozen scene."""

import hashlib
import math
from pathlib import Path

from pipeline.evidence import digest


def signed_planar_uv(position, normal, meters):
    if not math.isfinite(meters) or meters <= 0:
        raise ValueError("Texture scale must be positive")
    axis = max(range(3), key=lambda index: abs(normal[index]))
    if abs(abs(normal[axis]) - 1) > 1e-5 or any(
            abs(normal[index]) > 1e-5 for index in range(3) if index != axis):
        raise ValueError("Unsupported non-axis-aligned box projection")
    x, y, z = (value / meters for value in position)
    if axis == 0:
        return (1 - y if normal[0] < 0 else y, z)
    if axis == 1:
        return (1 - x if normal[1] > 0 else x, z)
    return (1 - y if normal[2] > 0 else y, x)


def normal_pixels(height, meters, distance, strength):
    import numpy as np

    dy = (np.roll(height, -1, axis=0) - np.roll(height, 1, axis=0)) * height.shape[0] / (2 * meters)
    dx = (np.roll(height, -1, axis=1) - np.roll(height, 1, axis=1)) * height.shape[1] / (2 * meters)
    normal = np.stack((-distance * dx, -distance * dy, np.ones_like(height)), axis=-1)
    normal /= np.linalg.norm(normal, axis=-1, keepdims=True)
    normal *= strength
    normal[:, :, 2] += 1 - strength
    normal /= np.linalg.norm(normal, axis=-1, keepdims=True)
    rgba = np.ones((*height.shape, 4), dtype=np.float32)
    rgba[:, :, :3] = normal * 0.5 + 0.5
    return rgba


def _save_image(image, path):
    image.filepath_raw = str(path)
    image.file_format = "PNG"
    image.save()
    image.pack()
    return {"name": path.stem, "sha256": digest(path),
            "width": image.size[0], "height": image.size[1]}


def _derive_normal(image, path, meters, distance, strength):
    import bpy
    import numpy as np

    width, height = image.size
    pixels = np.empty(width * height * 4, dtype=np.float32)
    image.pixels.foreach_get(pixels)
    values = pixels.reshape(height, width, 4)[:, :, :3].mean(axis=2)
    normal = bpy.data.images.new(path.stem, width=width, height=height, alpha=False)
    normal.colorspace_settings.name = "Non-Color"
    normal.pixels.foreach_set(normal_pixels(values, meters, distance, strength).ravel())
    record = _save_image(normal, path)
    record["usage"] = "normal"
    return normal, record


def _carbon_bake(scene, carbon, output, resolution):
    import bpy
    import numpy as np

    objects = sorted(
        (obj for obj in scene.objects if obj.type == "MESH" and
         any(slot.material == carbon for slot in obj.material_slots)),
        key=lambda obj: obj.name)
    if not objects:
        raise ValueError("Carbon geometry is missing")
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.select_set(True)
        if not obj.data.uv_layers:
            obj.data.uv_layers.new(name="PortableUV")
    bpy.context.view_layer.objects.active = objects[0]
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=0.006,
                             area_weight=0, correct_aspect=True, scale_to_bounds=False)
    bpy.ops.object.mode_set(mode="OBJECT")
    layout = hashlib.sha256()
    for obj in objects:
        values = np.empty(len(obj.data.uv_layers.active.data) * 2, dtype=np.float32)
        obj.data.uv_layers.active.data.foreach_get("uv", values)
        layout.update(obj.name.encode())
        layout.update(values.tobytes())
    image = bpy.data.images.new("carbon-color", width=resolution, height=resolution, alpha=False)
    image.colorspace_settings.name = "sRGB"
    materials = set(slot.material for obj in objects for slot in obj.material_slots)
    restore = []
    for mat in materials:
        nodes, links = mat.node_tree.nodes, mat.node_tree.links
        bsdf = next(node for node in nodes if node.type == "BSDF_PRINCIPLED")
        material_output = next(node for node in nodes if node.type == "OUTPUT_MATERIAL")
        original = material_output.inputs["Surface"].links[0].from_socket
        emission = nodes.new("ShaderNodeEmission")
        base = bsdf.inputs["Base Color"]
        if base.is_linked:
            links.new(base.links[0].from_socket, emission.inputs["Color"])
        else:
            emission.inputs["Color"].default_value = base.default_value
        links.new(emission.outputs[0], material_output.inputs["Surface"])
        target = nodes.new("ShaderNodeTexImage")
        target.image = image
        nodes.active = target
        restore.append((mat, original, material_output, emission, target))
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 1
    scene.cycles.seed = 42
    scene.render.threads_mode = "FIXED"
    scene.render.threads = 4
    bpy.ops.object.bake(type="EMIT", margin=4, margin_type="EXTEND", use_clear=True)
    record = _save_image(image, output / "carbon-color.png")
    record["usage"] = "carbon"
    for mat, original, material_output, emission, target in restore:
        mat.node_tree.links.new(original, material_output.inputs["Surface"])
        mat.node_tree.nodes.remove(emission)
        mat.node_tree.nodes.remove(target)
    nodes, links = carbon.node_tree.nodes, carbon.node_tree.links
    bsdf = next(node for node in nodes if node.type == "BSDF_PRINCIPLED")
    for node in list(nodes):
        if node.type not in {"BSDF_PRINCIPLED", "OUTPUT_MATERIAL"}:
            nodes.remove(node)
    texture = nodes.new("ShaderNodeTexImage")
    texture.image = image
    links.new(texture.outputs["Color"], bsdf.inputs["Base Color"])
    return record, {
        "objects": [obj.name for obj in objects], "resolution": resolution,
        "marginPixels": 4, "islandMargin": 0.006, "angleDegrees": 66,
        "samples": 1, "seed": 42, "pass": "EMIT", "device": "CPU", "threads": 4,
        "uvLayoutSha256": layout.hexdigest(),
    }


def prepare_materials(scene, staging_dir, recipe, source_hashes):
    import bpy

    output = Path(staging_dir)
    output.mkdir(exist_ok=False)
    groups, records, normals = {}, {}, {}
    carbon = None
    for material in sorted({slot.material for obj in scene.objects
                            for slot in obj.material_slots}, key=lambda mat: mat.name):
        nodes, links = material.node_tree.nodes, material.node_tree.links
        textures = [node for node in nodes if node.type == "TEX_IMAGE"]
        if any(node.type == "TEX_CHECKER" for node in nodes):
            if carbon is not None:
                raise ValueError("More than one procedural carbon material")
            carbon = material
            continue
        if not textures:
            if any(node.type not in {"BSDF_PRINCIPLED", "OUTPUT_MATERIAL"} for node in nodes):
                raise ValueError(f"Unsupported shader graph: {material.name}")
            continue
        if len(textures) != 3 or any(node.projection != "BOX" for node in textures):
            raise ValueError(f"Unsupported image projection: {material.name}")
        asset = "Asphalt012" if textures[0].image.name.startswith("Asphalt012_") else "Bricks059"
        meters = recipe["asphalt_tile_meters" if asset == "Asphalt012" else "brick_tile_meters"]
        scale = next(node for node in nodes if node.type == "VECT_MATH")
        if scale.operation != "SCALE" or abs(scale.inputs["Scale"].default_value - 1 / meters) > 1e-6:
            raise ValueError("Source texture scale differs from recipe")
        groups[material.name] = meters
        legacy_tint = next(node for node in nodes if node.type == "MIX_RGB")
        if legacy_tint.blend_type != "MULTIPLY" or legacy_tint.inputs[0].default_value != 1:
            raise ValueError("Unsupported source tint operation")
        tint = nodes.new("ShaderNodeMix")
        tint.data_type = "RGBA"
        tint.blend_type = "MULTIPLY"
        tint.inputs[0].default_value = 1
        tint_a = next(socket for socket in tint.inputs if socket.identifier == "A_Color")
        tint_b = next(socket for socket in tint.inputs if socket.identifier == "B_Color")
        tint_b.default_value = legacy_tint.inputs[2].default_value
        links.new(legacy_tint.inputs[1].links[0].from_socket, tint_a)
        color_output = next(socket for socket in tint.outputs if socket.identifier == "Result_Color")
        bsdf = next(node for node in nodes if node.type == "BSDF_PRINCIPLED")
        links.new(color_output, bsdf.inputs["Base Color"])
        nodes.remove(legacy_tint)
        channels = {}
        hashes = {}
        for node in textures:
            channel = next((channel for channel in ("Color", "Roughness", "Displacement")
                            if node.image.name == f"{asset}_1K-JPG_{channel}.jpg"), None)
            if channel is None or not node.image.packed_file:
                raise ValueError("Expected packed source texture is missing")
            checksum = hashlib.sha256(node.image.packed_file.data).hexdigest()
            if source_hashes.get(node.image.name) != checksum:
                raise ValueError("Packed texture differs from retained source hash")
            channels[channel], hashes[channel] = node, checksum
            node.projection = "FLAT"
            for link in list(node.inputs["Vector"].links):
                links.remove(link)
        bump = next(node for node in nodes if node.type == "BUMP")
        if asset not in normals:
            normals[asset] = _derive_normal(
                channels["Displacement"].image, output / f"{asset}-normal.png", meters,
                bump.inputs["Distance"].default_value, bump.inputs["Strength"].default_value)
        image, normal_record = normals[asset]
        bsdf = next(node for node in nodes if node.type == "BSDF_PRINCIPLED")
        normal_map = nodes.new("ShaderNodeNormalMap")
        normal_map.uv_map = "PortableUV"
        normal_texture = nodes.new("ShaderNodeTexImage")
        normal_texture.image = image
        links.new(normal_texture.outputs["Color"], normal_map.inputs["Color"])
        links.new(normal_map.outputs["Normal"], bsdf.inputs["Normal"])
        for node in list(nodes):
            if node.type in {"BUMP", "NEW_GEOMETRY", "VECT_MATH"} or node == channels["Displacement"]:
                nodes.remove(node)
        records[asset] = {
            "id": asset, "sourceUrl": f"https://ambientcg.com/a/{asset}",
            "license": "CC0-1.0",
            "licenseUrl": "https://creativecommons.org/publicdomain/zero/1.0/",
            "inputHashes": {"color": hashes["Color"], "roughness": hashes["Roughness"],
                            "height": hashes["Displacement"]},
            "tileMeters": meters, "recipeVersion": recipe["version"],
            "generatedTextures": [normal_record],
            "approximations": ["Height-derived tangent normals approximate the source bump filtering."],
        }
    if len(groups) != 7 or carbon is None:
        raise ValueError("Expected seven box-projected materials and one carbon graph")
    for obj in scene.objects:
        if obj.type != "MESH" or not any(slot.material.name in groups for slot in obj.material_slots):
            continue
        uv = obj.data.uv_layers.new(name="PortableUV")
        for face in obj.data.polygons:
            material = obj.material_slots[face.material_index].material
            if material.name not in groups:
                raise ValueError("Mixed textured and untextured surface is unsupported")
            for index in face.loop_indices:
                point = obj.matrix_world @ obj.data.vertices[obj.data.loops[index].vertex_index].co
                uv.data[index].uv = signed_planar_uv(point, face.normal, groups[material.name])
    record, bake = _carbon_bake(scene, carbon, output, recipe["carbon_resolution"])
    records["original-carbon"] = {
        "id": "original-carbon", "sourceUrl": "https://github.com/ridermw/street-scene-showcase",
        "license": "Original procedural work", "licenseUrl": None,
        "inputHashes": {"color": None, "roughness": None, "height": None},
        "tileMeters": None, "recipeVersion": recipe["version"], "generatedTextures": [record],
        "approximations": ["Finite atlas resolution approximates the procedural carbon weave."],
    }
    return {"materials": list(records.values()), "texturedGroups": groups, "carbonBake": bake}
