"""Original, unbranded parked vehicles; metres, +Y forward, Z up.

Only mesh/material datablocks are created. No operators, external assets,
scene settings, modifiers, or selection changes are required.
"""

import math

import bpy
import bmesh
from mathutils import Vector


class _Mesh:
    """Batch disconnected details by material to keep construction inexpensive."""

    def __init__(self):
        self.vertices = []
        self.faces = []

    def add(self, vertices, faces):
        offset = len(self.vertices)
        self.vertices.extend(vertices)
        self.faces.extend(tuple(offset + i for i in face) for face in faces)

    def tube(self, points, radius, sides=6, closed=False):
        points = [Vector(p) for p in points]
        vertices = []
        for i, point in enumerate(points):
            previous = points[(i - 1) % len(points)] if closed or i else point
            following = points[(i + 1) % len(points)] if closed or i < len(points) - 1 else point
            tangent = (following - previous).normalized()
            axis = Vector((0, 0, 1))
            if abs(tangent.dot(axis)) > .95:
                axis = Vector((0, 1, 0))
            u = tangent.cross(axis).normalized()
            v = tangent.cross(u).normalized()
            for j in range(sides):
                angle = math.tau * j / sides
                vertices.append(tuple(point + radius * (u * math.cos(angle) + v * math.sin(angle))))
        faces = []
        for i in range(len(points) if closed else len(points) - 1):
            k = (i + 1) % len(points)
            for j in range(sides):
                n = (j + 1) % sides
                faces.append((i * sides + j, i * sides + n, k * sides + n, k * sides + j))
        if not closed:
            faces.extend((tuple(reversed(range(sides))),
                          tuple((len(points) - 1) * sides + j for j in range(sides))))
        self.add(vertices, faces)

    def ellipsoid(self, center, scale, rings=6, segments=12):
        vertices = [(center[0], center[1], center[2] - scale[2])]
        for i in range(1, rings):
            latitude = -math.pi / 2 + math.pi * i / rings
            for j in range(segments):
                longitude = math.tau * j / segments
                vertices.append((center[0] + scale[0] * math.cos(latitude) * math.cos(longitude),
                                 center[1] + scale[1] * math.cos(latitude) * math.sin(longitude),
                                 center[2] + scale[2] * math.sin(latitude)))
        top = len(vertices)
        vertices.append((center[0], center[1], center[2] + scale[2]))
        faces = [(0, 1 + (j + 1) % segments, 1 + j) for j in range(segments)]
        for i in range(rings - 2):
            for j in range(segments):
                a = 1 + i * segments + j
                b = 1 + i * segments + (j + 1) % segments
                faces.append((a, b, b + segments, a + segments))
        faces.extend((top, top - segments + j, top - segments + (j + 1) % segments)
                     for j in range(segments))
        self.add(vertices, faces)

    def lathe_x(self, side, y, z, profile, segments=40):
        """Revolve (absolute lateral position, radius) pairs about a wheel axle."""
        vertices = [(side * x, y + r * math.cos(math.tau * j / segments),
                     z + r * math.sin(math.tau * j / segments))
                    for x, r in profile for j in range(segments)]
        faces = []
        for i in range(len(profile) - 1):
            for j in range(segments):
                n = (j + 1) % segments
                faces.append((i * segments + j, i * segments + n,
                              (i + 1) * segments + n, (i + 1) * segments + j))
        self.add(vertices, faces)

    def finish(self, name, material, root, smooth=True):
        if not self.faces:
            return
        mesh = bpy.data.meshes.new(name)
        mesh.from_pydata(self.vertices, [], self.faces)
        mesh.update()
        # Reflections on mirrored closed pieces need consistent outward normals.
        bm = bmesh.new()
        bm.from_mesh(mesh)
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        bm.to_mesh(mesh)
        bm.free()
        for polygon in mesh.polygons:
            polygon.use_smooth = smooth
        obj = bpy.data.objects.new(name, mesh)
        bpy.context.collection.objects.link(obj)
        obj.parent = root
        mesh.materials.append(material)
        return obj


def _material(name, color, metallic=0, roughness=.4, coat=0):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (*color[:3], 1)
    mat.use_nodes = True
    shader = mat.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = (*color[:3], 1)
    shader.inputs["Metallic"].default_value = metallic
    shader.inputs["Roughness"].default_value = roughness
    for key in ("Coat Weight", "Clearcoat"):
        if key in shader.inputs:
            shader.inputs[key].default_value = coat
            break
    return mat


def _sample(stations, y):
    if y <= stations[0][0]:
        return stations[0][1:]
    for a, b in zip(stations, stations[1:]):
        if y <= b[0]:
            t = (y - a[0]) / (b[0] - a[0])
            return tuple(x + (v - x) * t for x, v in zip(a[1:], b[1:]))
    return stations[-1][1:]


def _loft(mesh, rings, caps=True):
    count = len(rings[0])
    vertices = [p for ring in rings for p in ring]
    faces = [(i * count + j, i * count + (j + 1) % count,
              (i + 1) * count + (j + 1) % count, (i + 1) * count + j)
             for i in range(len(rings) - 1) for j in range(count)]
    if caps:
        faces.extend((tuple(reversed(range(count))),
                      tuple((len(rings) - 1) * count + j for j in range(count))))
    mesh.add(vertices, faces)


def _panel(mesh, points):
    """Convex panel triangulated around its center; avoids nonplanar n-gons."""
    center = tuple(sum(p[i] for p in points) / len(points) for i in range(3))
    mesh.add([center] + points,
             [(0, i + 1, (i + 1) % len(points) + 1) for i in range(len(points))])


def build_parked(name, kind='sedan', location=(0, 0, 0), color=(.15, .17, .19)):
    """Return an EMPTY with every generated mesh directly parented to it.

    Sedan body: 1.85 x 4.7 x 1.45 m; minivan: 1.95 x 4.9 x 1.8 m.
    Width excludes mirrors. Tire bottoms lie at local Z=0. `location` moves
    the root only, so callers can subsequently rotate or scale the whole car.
    Construction is bounded (roughly 15k vertices), with no evaluated modifiers.
    """
    if kind not in ('sedan', 'minivan'):
        raise ValueError("kind must be 'sedan' or 'minivan'")
    van = kind == 'minivan'
    width, length, height = (1.95, 4.9, 1.8) if van else (1.85, 4.7, 1.45)
    half = width / 2
    end = length / 2
    belt = 1.035 if van else .96
    radius = .355 if van else .33
    wheel_y = (-1.49, 1.49) if van else (-1.40, 1.40)
    arch = radius + .075
    root = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(root)
    root.empty_display_type = 'PLAIN_AXES'
    root.empty_display_size = .35
    root.location = location
    root["vehicle_kind"] = kind
    root["nominal_body_dimensions"] = (width, length, height)
    root["provenance"] = "Original parametric geometry; no brands or imported assets"
    batches = {key: _Mesh() for key in
               ('paint', 'rubber', 'glass', 'alloy', 'dark_metal', 'red', 'clear', 'plate')}
    paint, rubber, glass, alloy, dark, red, clear, plate = (
        batches[k] for k in ('paint', 'rubber', 'glass', 'alloy', 'dark_metal', 'red', 'clear', 'plate'))

    body_stations = [
        (-end, half * .82, belt - .15),
        (-end + .075, half * .94, belt - .085),
        (-end + .24, half * .99, belt - .005),
        (-1.72, half, belt + .015),
        (-.70, half * .99, belt),
        (.65, half * .99, belt),
        (1.62, half, belt - .025),
        (end - .25, half * .97, belt - .12),
        (end - .075, half * .92, belt - .19),
        (end, half * .80, belt - .24),
    ]
    samples = {p[0] for p in body_stations}
    samples.update(-end + length * i / 60 for i in range(61))
    for wy in wheel_y:
        samples.update(wy + arch * math.cos(math.pi * i / 24) for i in range(25))
    rings = []
    for y in sorted(samples):
        w, top = _sample(body_stations, y)
        bottom = .25
        for wy in wheel_y:
            if abs(y - wy) < arch:
                bottom = max(bottom, radius + math.sqrt(max(0, arch ** 2 - (y - wy) ** 2)))
        shoulder = max(bottom + .035, top - .16)
        # Flattened crown, radiused shoulders, and pinched rocker: not a box.
        ring = [(0, y, bottom), (.82*w, y, bottom), (.965*w, y, bottom+.015),
                (w, y, shoulder), (.985*w, y, top-.075),
                (.90*w, y, top-.016), (.68*w, y, top+.018),
                (0, y, top+.03), (-.68*w, y, top+.018),
                (-.90*w, y, top-.016), (-.985*w, y, top-.075),
                (-w, y, shoulder), (-.965*w, y, bottom+.015), (-.82*w, y, bottom)]
        rings.append(ring)
    _loft(paint, rings)

    cabin = ([(-2.24, .91*half, .79*half, belt+.045),
              (-1.96, .96*half, .79*half, height-.055),
              (-1.68, .96*half, .80*half, height-.005),
              (.46, .96*half, .79*half, height),
              (.70, .95*half, .78*half, height-.075),
              (1.43, .91*half, .77*half, belt+.025)]
             if van else
             [(-1.65, .94*half, .76*half, belt+.025),
              (-.87, .96*half, .77*half, height-.035),
              (-.61, .96*half, .78*half, height),
              (.44, .96*half, .77*half, height-.005),
              (.61, .95*half, .76*half, height-.055),
              (1.28, .91*half, .75*half, belt+.018)])
    cabin_rings = []
    for y, base_w, roof_w, top in cabin:
        cabin_rings.append([
            (-base_w, y, belt-.045), (base_w, y, belt-.045),
            (base_w, y, belt+.025), (roof_w+.035, y, top-.055),
            (roof_w, y, top-.015), (.5*roof_w, y, top-.003),
            (0, y, top), (-.5*roof_w, y, top-.003),
            (-roof_w, y, top-.015), (-roof_w-.035, y, top-.055),
            (-base_w, y, belt+.025)])
    _loft(paint, cabin_rings)

    def side_point(side, y, z, offset=.007):
        base_w, roof_w, top = _sample(cabin, y)
        t = max(0, min(1, (z - belt - .025) / max(.01, top - .055 - belt - .025)))
        return (side * (base_w + (roof_w + .035 - base_w) * t + offset), y, z)

    def side_window(side, outline):
        points = [side_point(side, y, z) for y, z in outline]
        _panel(glass, points)
        rubber.tube([side_point(side, y, z, .011) for y, z in outline], .012, closed=True)

    for side in (-1, 1):
        if van:
            outlines = [
                [(-2.13, belt+.12), (-1.91, height-.145), (-1.24, height-.105),
                 (-1.24, belt+.105)],
                [(-1.15, belt+.105), (-1.15, height-.105), (-.10, height-.10),
                 (-.10, belt+.105)],
                [(0, belt+.105), (0, height-.10), (.57, height-.145),
                 (1.24, belt+.105)],
            ]
        else:
            outlines = [
                [(-1.43, belt+.085), (-.80, height-.14), (-.24, height-.10),
                 (-.24, belt+.085)],
                [(-.14, belt+.085), (-.14, height-.10), (.51, height-.13),
                 (1.08, belt+.085)],
            ]
        for outline in outlines:
            side_window(side, outline)

    def roof_point(y, u, lift=.006):
        _, rw, top = _sample(cabin, y)
        return (u*rw, y, top - .015*abs(u) + lift)

    def screen(y0, y1):
        # Tessellation follows the actual sloping loft rather than a glass slab.
        rows, columns = 8, 12
        vertices = []
        for i in range(rows + 1):
            y = y0 + (y1-y0)*i/rows
            for j in range(columns + 1):
                u = -.94 + 1.88*j/columns
                vertices.append(roof_point(y, u))
        glass.add(vertices, [(i*(columns+1)+j, i*(columns+1)+j+1,
                              (i+1)*(columns+1)+j+1, (i+1)*(columns+1)+j)
                             for i in range(rows) for j in range(columns)])
        edge = ([roof_point(y0, -.94+1.88*j/columns, .012) for j in range(columns+1)]
                + [roof_point(y0+(y1-y0)*i/rows, .94, .012) for i in range(1, rows+1)]
                + [roof_point(y1, .94-1.88*j/columns, .012) for j in range(1, columns+1)]
                + [roof_point(y1-(y1-y0)*i/rows, -.94, .012) for i in range(1, rows)])
        rubber.tube(edge, .012, closed=True)

    screen(-2.205, -1.995) if van else screen(-1.53, -.935)
    screen(.765, 1.325) if van else screen(.665, 1.17)
    # Rear wiper for the tall hatch; understated defroster lines for the sedan.
    if van:
        rubber.tube([roof_point(-2.18, -.04, .025), roof_point(-2.09, .58, .025)], .013)
    else:
        for i in range(5):
            y = -1.42 + .09*i
            dark.tube([roof_point(y, -.83, .010), roof_point(y, .83, .010)], .0025, sides=4)

    for side in (-1, 1):
        for wy in wheel_y:
            lip_points = [(side*(half+.004), wy+arch*math.cos(math.pi*i/32),
                           radius+arch*math.sin(math.pi*i/32)) for i in range(33)]
            paint.tube(lip_points, .018, sides=8)
            rubber.tube([(side*(half-.016), y, z-.009) for _, y, z in lip_points], .018)
            outer, inner = half-.004, half-.225
            rubber.lathe_x(side, wy, radius,
                           [(inner, .22), (inner-.008, radius-.065),
                            (inner+.025, radius-.016), (inner+.06, radius),
                            (outer-.06, radius), (outer-.022, radius-.014),
                            (outer, radius-.06), (outer+.002, .22), (inner, .22)])
            # Sidewall rings, rim lips, dark brake disc and individual alloy spokes.
            for rr in (radius-.052, radius-.075):
                rubber.lathe_x(side, wy, radius,
                               [(outer-.001, rr-.003), (outer+.004, rr),
                                (outer-.001, rr+.003)], segments=40)
            dark.lathe_x(side, wy, radius, [(outer-.027, 0), (outer-.027, .209),
                                          (outer-.015, .209), (outer-.015, 0)])
            alloy.lathe_x(side, wy, radius, [(outer-.01, .192), (outer+.009, .203),
                                           (outer+.012, .219), (outer-.005, .227),
                                           (outer-.02, .214)], segments=40)
            for j in range(7):
                angle = math.tau*j/7
                points = []
                for r, a in ((.067, angle-.18), (.205, angle-.11),
                             (.205, angle+.10), (.067, angle+.25)):
                    points.append((side*(outer+.011), wy+r*math.cos(a), radius+r*math.sin(a)))
                _panel(alloy, points)
            alloy.lathe_x(side, wy, radius, [(outer+.012, 0), (outer+.012, .072),
                                           (outer+.018, .067), (outer+.018, 0)], segments=24)
            for j in range(5):
                a = math.tau*j/5
                dark.ellipsoid((side*(outer+.022), wy+.045*math.cos(a),
                                radius+.045*math.sin(a)), (.004, .009, .009), 4, 6)
            # Sparse tread sipes give tires structure without a heavy torus mesh.
            for j in range(36):
                a = math.tau*j/36
                points = [(side*x, wy+(radius-.002)*math.cos(a+da),
                           radius+(radius-.002)*math.sin(a+da))
                          for x, da in ((inner+.067, -.026), (outer-.075, .026))]
                dark.tube(points, .002, sides=4)

        def body_point(y, z, offset=.007):
            w, top = _sample(body_stations, y)
            # Match the loft's shoulder and rocker taper, so seams sit on paint.
            bottom = .25
            for wy in wheel_y:
                if abs(y-wy) < arch:
                    bottom = max(bottom, radius+math.sqrt(max(0, arch*arch-(y-wy)**2)))
            shoulder = max(bottom+.035, top-.16)
            levels = [(bottom+.015, .965*w), (shoulder, w),
                      (top-.075, .985*w), (top-.016, .90*w)]
            x = _sample(levels, z)[0]
            return (side*(x+offset), y, z)

        door_edges = (-1.17, -.045, 1.11) if van else (-1.07, -.19, 1.05)
        for y in door_edges:
            bottom = .37
            for wy in wheel_y:
                if abs(y-wy) < arch:
                    bottom = max(bottom, radius+math.sqrt(arch*arch-(y-wy)**2)+.04)
            points = [body_point(y, bottom+(belt-.04-bottom)*i/8) for i in range(9)]
            rubber.tube(points, .0045, sides=4)
        for y in ((-.96, .17) if van else (-.82, .10)):
            z = belt-.15
            x = abs(body_point(y, z)[0])
            rubber.ellipsoid((side*(x+.005), y, z), (.008, .10, .024), 4, 10)
            alloy.tube([(side*(x+.024), y-.072, z+.003),
                        (side*(x+.028), y+.058, z+.003)], .011)
        # Rocker strip and, on the minivan, a sliding-door track.
        rubber.tube([body_point(y, .34) for y in (-.93, -.5, 0, .5, .93)], .018)
        if van:
            rubber.tube([body_point(y, .89) for y in (-1.96, -1.5, -1.0, -.6)], .008)
        mirror_y = .91 if van else .88
        rubber.tube([side_point(side, mirror_y, belt+.13),
                     (side*(half+.09), mirror_y, belt+.14)], .031, sides=8)
        paint.ellipsoid((side*(half+.13), mirror_y, belt+.17), (.135, .16, .075))
        glass.ellipsoid((side*(half+.145), mirror_y-.125, belt+.175), (.100, .008, .049))
        # Short side molding picks up long highlights in the reference view.
        alloy.tube([body_point(y, .52) for y in (-.90, -.4, .4, .90)], .006, sides=4)

    def rear_point(x, z, offset=.008):
        # Rear fascia is flat centrally and rolls around the outer corners.
        corner = max(0, (abs(x)/half-.82)/.12)
        y = -end + .075*corner
        return (x, y-offset, z)

    for side in (-1, 1):
        lamp = [(side*x, z) for x, z in
                ((.43, belt-.13), (.78, belt-.13), (.87, belt-.17),
                 (.84, belt-.30), (.53, belt-.27), (.43, belt-.21))]
        points = [rear_point(x, z, .033) for x, z in lamp]
        _panel(red, points)
        rubber.tube(points, .009, closed=True)
        _panel(clear, [rear_point(side*x, z, .038) for x, z in
                       ((.55, belt-.235), (.81, belt-.255),
                        (.80, belt-.28), (.55, belt-.26))])
        # Wraparound side lens, not a floating rear rectangle.
        _panel(red, [(side*half*.95, -end+.11, belt-.15),
                     (side*half*.993, -end+.35, belt-.07),
                     (side*half*.997, -end+.35, belt-.22),
                     (side*half*.96, -end+.12, belt-.28)])
        rubber.tube([rear_point(side*.67, .38), rear_point(side*.83, .39)], .025)
        red.tube([rear_point(side*.67, .39, .038), rear_point(side*.81, .40, .038)], .011)
        # Front lamp panels follow the hood's tapered nose.
        _panel(clear, [(side*.44, end-.045, belt-.22),
                       (side*.75, end-.065, belt-.21),
                       (side*.84, end-.16, belt-.12),
                       (side*.49, end-.17, belt-.13)])

    hatch = ([(-.76, belt-.14), (-.78, .52), (-.63, .43), (.63, .43),
              (.78, .52), (.76, belt-.14)]
             if van else [(-.72, belt-.14), (-.65, .67), (-.46, .61),
                          (.46, .61), (.65, .67), (.72, belt-.14)])
    rubber.tube([rear_point(x, z, .018) for x, z in hatch], .006, sides=5)
    # Deck/liftgate upper seams join the rear surface to the cabin pillars.
    if van:
        for side in (-1, 1):
            rubber.tube([rear_point(side*.76, belt-.14, .018),
                         (side*.83, -2.22, belt+.07),
                         (side*.79, -1.975, height-.11)], .006)
        red.tube([roof_point(-1.986, -.27, .022),
                  roof_point(-1.986, .27, .022)], .012)
    else:
        rubber.tube([(x, -1.79, _sample(body_stations, -1.79)[1]+.032)
                     for x in (-.62, -.3, 0, .3, .62)], .005)
    # Plate recess, border, and fictional characters.
    for target, w, h, z, offset in ((rubber, .57, .25, .67 if van else .51, .026),
                                   (plate, .47, .17, .67 if van else .51, .033)):
        _panel(target, [rear_point(x, zz, offset) for x, zz in
                        ((-w/2, z-h/2), (w/2, z-h/2), (w/2, z+h/2), (-w/2, z+h/2))])
    alloy.tube([rear_point(-.18, .85 if van else .77, .04),
                rear_point(.18, .85 if van else .77, .04)], .014)
    for direction in (-1, 1):
        # A rounded lower bumper and separation line, kept inside nominal length.
        y = direction*(end-.035)
        rubber.tube([(x, y-direction*.075*max(0, (abs(x)/half-.82)/.12), .34)
                     for x in (-.77, -.55, 0, .55, .77)], .040, sides=8)
        rubber.tube([(x, direction*(end+.002-.075*max(0, (abs(x)/half-.82)/.12)), .45)
                     for x in (-.8, -.55, 0, .55, .8)], .005, sides=4)
    for z in (.49, .54, .59):
        dark.tube([(-.42, end-.008, z), (.42, end-.008, z)], .016)
    dark.tube([(-.59, -end+.10, .255), (-.59, -end+.025, .255)], .045, sides=12)

    materials = {
        'paint': _material(name+" | enamel", color, .42, .16, .70),
        'rubber': _material(name+" | rubber and seals", (.012, .015, .018), .0, .69),
        'glass': _material(name+" | dark inset glazing", (.016, .027, .037), .34, .16, .5),
        'alloy': _material(name+" | satin alloy", (.39, .42, .45), .83, .28),
        'dark_metal': _material(name+" | dark metal", (.038, .043, .047), .55, .49),
        'red': _material(name+" | red lenses", (.40, .009, .013), .20, .22, .5),
        'clear': _material(name+" | clear lenses", (.61, .67, .69), .33, .23, .4),
        'plate': _material(name+" | fictional plate", (.52, .54, .51), .1, .38),
    }
    for key, batch in batches.items():
        batch.finish(name+" | "+key, materials[key], root, smooth=key not in ('plate', 'clear', 'glass'))
    plate_text = bpy.data.curves.new(name+" | plate text curve", 'FONT')
    plate_text.body = "SCN 018"
    plate_text.align_x = 'CENTER'
    plate_text.align_y = 'CENTER'
    plate_text.size = .105 if van else .082
    plate_text.extrude = .002
    plate_text.resolution_u = 2
    text_obj = bpy.data.objects.new(name+" | plate text", plate_text)
    bpy.context.collection.objects.link(text_obj)
    text_obj.parent = root
    text_obj.location = rear_point(0, .67 if van else .51, .050)
    text_obj.rotation_euler = (math.radians(90), 0, 0)
    plate_text.materials.append(materials['dark_metal'])
    return root
