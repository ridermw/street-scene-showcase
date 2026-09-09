"""Original, hand-authored rear-chase supercar; metres, +Y forward, +Z up.

Structure: one root EMPTY owns all fixed meshes and four wheel-hub EMPTYs.
Each hub owns its tire, tread, barrel, rim, spokes, rotor and fasteners;
brake calipers are fixed to the root. Hub local X is the rolling axle.
No external assets, operators, animation, scene settings or file writes.
"""

import math

import bpy
import bmesh
from mathutils import Vector


def build_car(name="Hero", paint_color=(0.62, 0.012, 0.019, 1.0),
              location=(0, 0, 0)):
    """Return {'root': EMPTY, 'wheels': [FL, FR, RL, RR], 'radius': .36}.

    Nominal body envelope is 2.05 x 4.70 x 1.25 m, with tire contact at Z=0.
    The rear tire envelope is 2.35 m wide for the inferred chase silhouette.
    Parent-local geometry is built at the origin before applying ``location``.
    Paint accepts either linear RGB or RGBA. Construction uses native meshes
    and small bevel modifiers, not booleans or subdivision surfaces.
    """
    rgba = tuple(paint_color)
    if len(rgba) == 3:
        rgba += (1.0,)
    if len(rgba) != 4:
        raise ValueError("paint_color must contain three or four components")

    collection = bpy.context.collection

    def empty(label, parent=None, position=(0, 0, 0)):
        obj = bpy.data.objects.new(name + "." + label, None)
        collection.objects.link(obj)
        obj.parent = parent
        obj.location = position
        obj.empty_display_type = "PLAIN_AXES"
        obj.empty_display_size = 0.18
        return obj

    root = empty("Root")
    root["asset_origin"] = "Original procedural design; no third-party assets"
    root["forward_axis"] = "+Y"
    root["wheel_radius"] = 0.36

    def material(label, color, metallic=0.0, roughness=0.35,
                 coat=0.0, emission=None):
        mat = bpy.data.materials.new(name + "." + label)
        mat.use_nodes = True
        mat.diffuse_color = color
        shader = mat.node_tree.nodes.get("Principled BSDF")
        shader.inputs["Base Color"].default_value = color
        shader.inputs["Metallic"].default_value = metallic
        shader.inputs["Roughness"].default_value = roughness
        coat_input = shader.inputs.get("Coat Weight")
        if coat_input is None:
            coat_input = shader.inputs.get("Clearcoat")
        if coat_input is not None:
            coat_input.default_value = coat
        if emission is not None:
            socket = shader.inputs.get("Emission Color")
            if socket is None:
                socket = shader.inputs.get("Emission")
            socket.default_value = emission
            strength = shader.inputs.get("Emission Strength")
            if strength is not None:
                strength.default_value = 3.0
        return mat

    paint = material("Vermilion lacquer", rgba, 0.2, 0.14, 0.85)
    paint.node_tree.nodes.get("Principled BSDF").inputs["Coat Roughness"].default_value=.08
    carbon = material("Satin carbon", (0.012, 0.016, 0.020, 1), 0.32, 0.32)
    black = material("Intake darkness", (0.003, 0.004, 0.006, 1), 0.05, 0.7)
    rubber = material("Tire rubber", (0.022, 0.024, 0.027, 1), 0.0, 0.69)
    glass = material("Smoked cockpit", (0.012, 0.024, 0.033, 1), 0.48, 0.12, 0.6)
    engine_glass = material("Engine glass", (0.025, 0.037, 0.043, 1), 0.5, 0.19, 0.4)
    alloy = material("Forged graphite", (0.12, 0.145, 0.16, 1), 0.88, 0.25)
    metal = material("Machined titanium", (0.48, 0.53, 0.57, 1), 0.94, 0.23)
    rotor_mat = material("Brake rotor", (0.20, 0.22, 0.23, 1), 0.8, 0.45)
    caliper_mat = material("Caliper red", (0.43, 0.012, 0.008, 1), 0.45, 0.32)
    red_led = material("Unlit ruby lens", (0.24, 0.003, 0.008, 1),
                       0.12, 0.28, 0.35)
    grille_mat = material("Dark grille mesh", (0.008, 0.010, 0.012, 1),
                          0.25, 0.51)
    white_led = material("Headlamp LED", (0.72, 0.84, 0.95, 1), 0.1, 0.2,
                         emission=(0.65, 0.8, 1.0, 1))

    # Fine woven sheen remains subtle; the silhouette does not rely on textures.
    nodes = carbon.node_tree.nodes
    links = carbon.node_tree.links
    coords = nodes.new("ShaderNodeTexCoord")
    weave = nodes.new("ShaderNodeTexChecker")
    weave.inputs["Color1"].default_value = (0.009, 0.012, 0.016, 1)
    weave.inputs["Color2"].default_value = (0.024, 0.029, 0.034, 1)
    weave.inputs["Scale"].default_value = 155
    links.new(coords.outputs["Generated"], weave.inputs["Vector"])
    links.new(weave.outputs["Color"],
              nodes.get("Principled BSDF").inputs["Base Color"])

    def mesh(label, verts, faces, mat, parent=None, bevel=0.0, smooth=True):
        data = bpy.data.meshes.new(name + "." + label)
        data.from_pydata(verts, [], faces)
        data.update()
        bm = bmesh.new()
        bm.from_mesh(data)
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        bm.to_mesh(data)
        bm.free()
        obj = bpy.data.objects.new(name + "." + label, data)
        collection.objects.link(obj)
        obj.parent = root if parent is None else parent
        data.materials.append(mat)
        for polygon in data.polygons:
            polygon.use_smooth = smooth
        if bevel:
            mod = obj.modifiers.new("Small manufactured edge", "BEVEL")
            mod.width = bevel
            mod.segments = 2
            mod.limit_method = "ANGLE"
        return obj

    def grid(label, rows, mat, parent=None):
        width = len(rows[0])
        verts = [v for row in rows for v in row]
        faces = [(j * width + i, j * width + i + 1,
                  (j + 1) * width + i + 1, (j + 1) * width + i)
                 for j in range(len(rows) - 1) for i in range(width - 1)]
        return mesh(label, verts, faces, mat, parent)

    def prism(label, polygon, delta, mat, bevel=0.008, parent=None):
        count = len(polygon)
        verts = list(polygon) + [
            tuple(Vector(v) + Vector(delta)) for v in polygon]
        faces = [tuple(reversed(range(count))), tuple(range(count, count * 2))]
        faces += [(i, (i + 1) % count, (i + 1) % count + count, i + count)
                  for i in range(count)]
        return mesh(label, verts, faces, mat, parent, bevel, smooth=False)

    def tube(label, path, radius, mat, sides=8, closed=False, parent=None):
        points = [Vector(v) for v in path]
        verts = []
        count = len(points)
        for i, point in enumerate(points):
            before = points[(i - 1) % count] if closed else points[max(0, i - 1)]
            after = points[(i + 1) % count] if closed else points[min(count - 1, i + 1)]
            tangent = (after - before).normalized()
            reference = Vector((0, 0, 1))
            if abs(tangent.dot(reference)) > 0.93:
                reference = Vector((0, 1, 0))
            u = tangent.cross(reference).normalized()
            v = tangent.cross(u).normalized()
            for k in range(sides):
                angle = k * math.tau / sides
                verts.append(tuple(point + radius * (
                    math.cos(angle) * u + math.sin(angle) * v)))
        faces = []
        for i in range(count if closed else count - 1):
            nxt = (i + 1) % count
            for k in range(sides):
                faces.append((i * sides + k, i * sides + (k + 1) % sides,
                              nxt * sides + (k + 1) % sides, nxt * sides + k))
        if not closed:
            faces += [tuple(reversed(range(sides))),
                      tuple((count - 1) * sides + k for k in range(sides))]
        return mesh(label, verts, faces, mat, parent)

    def interpolate(stations, value):
        """Cubic Hermite interpolation with clamped endpoint tangents."""
        if value <= stations[0][0]:
            return stations[0][1:]
        if value >= stations[-1][0]:
            return stations[-1][1:]
        for index in range(len(stations) - 1):
            a, b = stations[index:index + 2]
            if a[0] <= value <= b[0]:
                prev = stations[max(index - 1, 0)]
                nxt = stations[min(index + 2, len(stations) - 1)]
                t = (value - a[0]) / (b[0] - a[0])
                result = []
                for column in range(1, len(a)):
                    m0 = (b[column] - prev[column]) / (b[0] - prev[0])
                    m1 = (nxt[column] - a[column]) / (nxt[0] - a[0])
                    d = b[0] - a[0]
                    result.append((2*t**3 - 3*t**2 + 1)*a[column]
                                  + (t**3 - 2*t**2 + t)*d*m0
                                  + (-2*t**3 + 3*t**2)*b[column]
                                  + (t**3 - t**2)*d*m1)
                return result

    # Y, half-width, deck centre height, shoulder height. Broad haunches
    # surround a deliberately narrower, lower engine cover at the rear.
    body_stations = [
        (-2.35, 0.86, 0.705, 0.75),
        (-2.20, 0.93, 0.745, 0.81),
        (-1.65, 0.975, 0.78, 0.91),
        (-1.12, 0.98, 0.80, 0.88),
        (-0.55, 0.93, 0.77, 0.76),
        (0.15, 0.895, 0.69, 0.72),
        (0.88, 0.96, 0.66, 0.80),
        (1.42, 0.99, 0.65, 0.86),
        (1.98, 0.945, 0.54, 0.66),
        (2.35, 0.83, 0.405, 0.47),
    ]

    def arch_bottom(y):
        bottom = 0.20
        for axle in (-1.43, 1.39):
            distance = abs(y - axle)
            if distance < 0.414:
                bottom = max(bottom, 0.36 + math.sqrt(0.414**2 - distance**2))
            elif distance < 0.48:
                bottom = max(bottom, 0.20 + 0.16 * (0.48 - distance) / 0.066)
        return bottom

    shoulder_slots=[-1.89+i*.113 for i in range(7)]

    def surface(y, t):
        width, center, shoulder = interpolate(body_stations, y)
        a = abs(t)
        z = center + (shoulder - center) * math.sin(a * math.pi / 2)**2
        z -= 0.09 * a**12
        # Preserve a visible red lip above the true open wheel wells.
        z += max(0.0, arch_bottom(y) + 0.034 - (shoulder - 0.09)) * a**8
        x=abs(t*width)
        if .73<x<.89:
            across=min(1,(x-.73)/.025,(.89-x)/.025)
            along=max(max(0,1-abs(y-center)/.019) for center in shoulder_slots)
            z-=.018*across*along
        return (t * width, y, z)

    def flank_tuck(y):
        return .055 + .065 * max(0, min(1, (-y-.95)/.65))

    y_samples = sorted(set([-2.35 + 4.7 * i / 144 for i in range(145)]
                           +[y+dy for y in shoulder_slots for dy in [-.019,0,.019]]))
    upper=grid("Continuous sculpted upper body",
               [[surface(y, -1 + 2*i/48) for i in range(49)] for y in y_samples],paint)
    upper.data.materials.append(black)
    for face in upper.data.polygons:
        if .745<abs(face.center.x)<.88 and any(abs(face.center.y-y)<.019 for y in shoulder_slots):
            face.material_index=1
    for sign, side in ((-1, "L"), (1, "R")):
        rows = []
        for y in y_samples:
            width, _, _ = interpolate(body_stations, y)
            top = surface(y, sign)[2]
            bottom = min(arch_bottom(y), top - 0.015)
            # Tuck the trailing quarter below the haunch; the rear tire
            # shoulders stay exposed without increasing the wheel track.
            lower_tuck = flank_tuck(y)
            rows.append([(sign * (width - 0.025 * math.sin(v * math.pi)
                                  - lower_tuck * v), y, top*(1-v) + bottom*v)
                         for v in (0, .15, .35, .6, .8, 1)])
        grid(side + " cutaway flank", rows, paint)
        for axle, label in ((-1.43, "rear"), (1.39, "front")):
            lip = []
            for i in range(49):
                a = math.pi * i / 48
                y = axle - 0.414 * math.cos(a)
                width = interpolate(body_stations, y)[0]
                lip.append((sign*(width - flank_tuck(y)), y,
                            .36 + .414*math.sin(a)))
            tube(side + " " + label + " arch edging", lip, .013, paint)
            tube(side + " " + label + " dark wheel well", [
                (x - sign*.019, y, z-.012) for x, y, z in lip], .024, black)

        # Side sills stay between the wheel apertures, not across the tires.
        prism(side + " carbon sill",
              [(sign*.90, -.98, .17), (sign*.965, -.93, .16),
               (sign*.94, .91, .16), (sign*.855, .94, .22)],
              (0, 0, .055), carbon, .012)
        intake = [(sign*.948, -.92, .37), (sign*.953, -.78, .68),
                  (sign*.914, -.22, .65), (sign*.90, -.49, .33)]
        prism(side + " side intake shadow", intake, (sign*.009, 0, 0), black)
        tube(side + " intake blade",
             [(sign*.962, -.89, .39), (sign*.947, -.63, .49),
              (sign*.922, -.29, .64)], .018, carbon)
        tube(side + " door shutline",
             [(sign*.91, -.12, .70), (sign*.899, -.12, .50),
              (sign*.875, .03, .29), (sign*.892, .70, .29),
              (sign*.917, .88, .61)], .003, black, sides=5)

    # Narrow continuous black canopy: its upper cap is a red floating roof.
    canopy_stations = [
        (-.98, .52, .83, .89), (-.86, .575, .84, 1.13),
        (-.73, .605, .83, 1.235),
        (-.36, .605, .82, 1.235), (.10, .605, .80, 1.24),
        (.43, .575, .78, 1.225), (.78, .60, .73, .99),
        (1.08, .66, .69, .705),
    ]

    def canopy(y, t, offset=0):
        width, edge, top = interpolate(canopy_stations, y)
        a = abs(t)
        crown = math.sqrt(max(0, 1-a**4))
        return (width*t, y, edge + (top-edge)*crown + offset)

    grid("Single smoked glass canopy",
         [[canopy(-.98+2.06*j/60, -1+2*i/40) for i in range(41)]
          for j in range(61)], glass)
    grid("Floating red roof",
         [[canopy(-.73+1.17*j/24, -.80+1.60*i/28, .009)
           for i in range(29)] for j in range(25)], paint)
    grid("Painted rear cockpit shoulder",
         [[canopy(-.98+.12*j/12,-1+2*i/32,.012)
           for i in range(33)] for j in range(13)],paint)
    tube("Straight rear roof header",
         [canopy(-.73, -.80+1.60*i/32, .011) for i in range(33)],
         .012, paint)
    for sign, side in ((-1, "L"), (1, "R")):
        tube(side + " roof rail",
             [canopy(-.76 + 1.77*i/40, sign*.90, .011) for i in range(41)],
             .021, paint)
        tube(side + " window lower gasket",
             [canopy(-.90 + 1.92*i/40, sign, .007) for i in range(41)],
             .012, carbon)
        tube(side + " window rear pillar",
             [canopy(-.63+.10*i/14, sign*(1-.12*i/14), .012)
              for i in range(15)], .021, paint)
        tube(side + " mirror arm",
             [(sign*.67, .63, .83), (sign*.88, .57, .84)], .022, carbon)
        # A small ellipsoidal loft gives the mirror a curved housing.
        mirror_rows = []
        for j in range(13):
            a = math.pi*j/12
            mirror_rows.append([
                (sign*(.87+.12*math.cos(a)),
                 .54+.075*math.sin(a)*math.cos(k*math.tau/20),
                 .85+.047*math.sin(a)*math.sin(k*math.tau/20))
                for k in range(21)])
        grid(side + " mirror shell", mirror_rows, paint)
        prism(side + " mirror glass",
              [(sign*.80, .473, .825), (sign*.95, .473, .831),
               (sign*.96, .473, .871), (sign*.81, .473, .878)],
              (0, .006, 0), glass, .009)

    def engine_cover(y, x):
        t=(y+2.05)/1.17
        base=surface(y,x/interpolate(body_stations,y)[0])[2]
        return base+.19*t*max(0,1-(abs(x)/.59)**6)

    grid("Raised red engine cover",
         [[(x,y,engine_cover(y,x)+.009) for x in [-.59+1.18*i/32 for i in range(33)]]
          for y in [-2.05+1.17*j/36 for j in range(37)]],paint)
    # Glazing and louvers follow the same raised cover surface.
    grid("Rear engine glass",
         [[(t*.52, y, engine_cover(y,t*.52)+.023)
           for t in [-1+2*i/20 for i in range(21)]]
          for y in [-1.50+.58*j/26 for j in range(27)]], engine_glass)
    for sign, side in ((-1, "L"), (1, "R")):
        tube(side + " engine cover rim",
             [(sign*.535, y, surface(y, sign*.535/interpolate(body_stations, y)[0])[2]+.025)
              for y in [-2.01+1.11*i/36 for i in range(37)]], .016, paint)
        # Red flying buttresses rise beside the rear glazing.
        rows = []
        for j in range(29):
            t = j/28
            y = -1.99 + 1.24*t
            xc = .67 - .06*t
            base = surface(y, sign*xc/interpolate(body_stations, y)[0])[2]
            rows.append([(sign*(xc + .105*u), y,
                          base + .025 + .135*math.sin(math.pi*t)*max(0, 1-u*u))
                         for u in [-1+2*i/12 for i in range(13)]])
        grid(side + " raised rear buttress", rows, paint)
    for i in range(6):
        y = -1.46+i*.085
        z = engine_cover(y,0)+.032
        prism("Engine glass louver %02d" % i,
              [(-.49, y-.015, z), (.49, y-.015, z),
               (.48, y+.019, z+.016), (-.48, y+.019, z+.016)],
              (0, 0, .014), carbon, .004)

    # Rear face: recessed black aperture, red shoulder edges, a thin
    # waistline, separate metal exhaust tunnels, and a broad diffuser.
    rear_outline = [(-.88, -2.327, .68), (-.86, -2.327, .42),
                    (-.79, -2.327, .18), (.79, -2.327, .18),
                    (.86, -2.327, .42), (.88, -2.327, .68)]
    prism("Recessed rear carbon mask", rear_outline, (0, .07, 0), carbon, .018)
    prism("Red rear waist",
          [(-.86, -2.35, .70), (-.54, -2.35, .60),
           (.54, -2.35, .60), (.86, -2.35, .70),
           (.77, -2.31, .76), (-.77, -2.31, .76)],
          (0, .08, 0), paint, .019)
    grille_outline = [(-.46, -2.367, .565), (.46, -2.367, .565),
                      (.36, -2.367, .295), (-.36, -2.367, .295)]
    prism("Central grille cavity", grille_outline, (0, .025, 0), black, .01)
    tube("Central grille perimeter", grille_outline, .012, alloy, closed=True)

    # Open honeycomb cells are aggregated into one modest mesh.
    honey_verts, honey_faces = [], []
    cell = .026
    for row in range(7):
        z = .315 + row*.034
        max_x = .35 + (z-.315)*.4
        for column in range(-12, 13):
            x = column*.043 + (row % 2)*.0215
            if abs(x) + cell > max_x:
                continue
            base = len(honey_verts)
            for radius in (cell, cell-.002):
                for k in range(6):
                    a = math.tau*k/6
                    honey_verts.append((x+radius*math.cos(a), -2.371,
                                        z+radius*math.sin(a)))
            for k in range(6):
                honey_faces.append((base+k, base+(k+1)%6,
                                    base+6+(k+1)%6, base+6+k))
    mesh("Open hexagonal rear grille", honey_verts, honey_faces, grille_mat,
         smooth=False)

    def rounded_rectangle(cx, y, cz, half_x, half_z, exponent=3.6, count=48):
        result = []
        for i in range(count):
            a = math.tau*i/count
            c, s = math.cos(a), math.sin(a)
            result.append((cx+half_x*math.copysign(abs(c)**(2/exponent), c),
                           y,
                           cz+half_z*math.copysign(abs(s)**(2/exponent), s)))
        return result

    for sign, side in ((-1, "L"), (1, "R")):
        cx = sign*.70
        # Deep black well behind a rounded rectangular titanium trumpet.
        surround = rounded_rectangle(cx, -2.345, .49, .147, .17)
        prism(side + " exhaust recess", surround, (0, .08, 0), black, .005)
        tube(side + " exhaust carbon bezel", surround, .018, carbon, closed=True)
        rings = [
            rounded_rectangle(cx, -2.292, .492, .091, .114),
            rounded_rectangle(cx, -2.383, .492, .126, .15),
            rounded_rectangle(cx, -2.391, .53, .065, .08),
            rounded_rectangle(cx, -2.243, .53, .06, .065),
        ]
        rings = [ring + [ring[0]] for ring in rings]
        grid(side + " hollow titanium exhaust", rings, metal)
        prism(side + " exhaust deep interior",
              rounded_rectangle(cx, -2.24, .53, .06, .065),
              (0, .006, 0), black, bevel=0)
        for i in range(7):
            x = cx+(i-3)*.027
            tube(side + " exhaust lower flute %d" % i,
                 [(x, -2.386, .35), (x, -2.39, .385),
                  (x, -2.35, .441)], .006, metal, sides=6)

        light_outline = [(sign*.55, -2.369, .637), (sign*.88, -2.338, .671),
                         (sign*.88, -2.334, .716), (sign*.52, -2.365, .682)]
        prism(side + " smoked tail lamp housing", light_outline,
              (0, .017, 0), glass, .006)
        for i in range(2):
            tube(side + " thin red tail light %d" % i,
                 [(sign*.565, -2.382, .651+i*.018),
                  (sign*.68, -2.379, .658+i*.018),
                  (sign*.865, -2.35, .685+i*.018)], .0045, red_led, sides=8)
        tube(side + " outer bumper return",
             [(sign*.90, -2.29, .69), (sign*.90, -2.26, .57),
              (sign*.88, -2.24, .35), (sign*.85, -2.25, .22)],
             .035, paint, sides=10)

    diffuser_rows = []
    for j in range(13):
        y = -2.35 + .70*j/12
        diffuser_rows.append([
            (t*.86, y, .133+.052*abs(t)**4+.115*j/12)
            for t in [-1+2*i/32 for i in range(33)]])
    grid("Broad rising diffuser tray", diffuser_rows, carbon)
    tube("Diffuser rear lip",
         [(t*.87, -2.355, .135+.054*abs(t)**4)
          for t in [-1+2*i/40 for i in range(41)]], .015, carbon)
    for i, x in enumerate((-.59, -.38, -.19, 0, .19, .38, .59)):
        prism("Diffuser vertical strake %d" % i,
              [(x, -2.36, .135), (x, -2.31, .31),
               (x, -1.71, .31), (x, -1.71, .247)],
              (.014, 0, 0), carbon, .003)
    prism("Central reverse lamp",
          [(-.065, -2.382, .222), (.065, -2.382, .222),
           (.052, -2.382, .25), (-.052, -2.382, .25)],
          (0, .009, 0), white_led, .003)

    # A thin red aerofoil with a carbon underside, supported by paired
    # swept uprights. Its short chord leaves the rear glazing visible.
    wing_rows = []
    for j in range(49):
        x = -1.015+2.03*j/48
        sweep = .025*(abs(x)/1.015)**2
        ring = []
        for i in range(33):
            angle = math.tau*i/32
            y = -1.88 + sweep + .085*math.cos(angle)
            z = 1.133 + .011*math.sin(angle) + .010*math.cos(angle)
            z += .010*(abs(x)/1.015)**2
            ring.append((x, y, z))
        wing_rows.append(ring)
    wing = grid("Thin red rear aerofoil", wing_rows, carbon)
    wing.data.materials.append(paint)
    for polygon in wing.data.polygons:
        if polygon.index % 32 < 16:
            polygon.material_index = 1
    tube("Wing red trailing edge",
         [(x, -1.965+.025*(abs(x)/1.015)**2,
           1.123+.010*(abs(x)/1.015)**2)
          for x in [-1.015+2.03*i/48 for i in range(49)]],
         .006, paint)
    for sign, side in ((-1, "L"), (1, "R")):
        x = sign*.70
        prism(side + " swept wing pylon",
              [(x, -1.86, .85), (x, -1.69, .87),
               (x, -1.81, 1.138), (x, -1.94, 1.121)],
              (sign*.035, 0, 0), carbon, .009)
        x = sign*1.013
        prism(side + " wing endplate",
              [(x, -1.99, 1.090), (x, -1.97, 1.190),
               (x, -1.77, 1.185), (x, -1.755, 1.110)],
              (sign*.018, 0, 0), paint, .012)

    # Front fascia and lights complete the asset for oblique chase views.
    prism("Front lower intake",
          [(-.78, 2.32, .25), (.78, 2.32, .25),
           (.72, 2.34, .39), (-.72, 2.34, .39)],
          (0, -.09, 0), black, .013)
    prism("Front red nose",
          [(-.83, 2.34, .39), (.83, 2.34, .39),
           (.78, 2.34, .47), (-.78, 2.34, .47)],
          (0, -.08, 0), paint, .018)
    tube("Front splitter",
         [(-.89, 2.23, .195), (-.77, 2.35, .19), (0, 2.365, .18),
          (.77, 2.35, .19), (.89, 2.23, .195)], .025, carbon)
    for sign, side in ((-1, "L"), (1, "R")):
        rows = []
        for j in range(9):
            y = 1.91+.27*j/8
            rows.append([(sign*x, y, surface(y, sign*x/interpolate(body_stations, y)[0])[2]+.011)
                         for x in (.59, .66, .73, .80)])
        grid(side + " headlight glass", rows, glass)
        tube(side + " headlight signature",
             [(sign*x, 2.12, surface(2.12, sign*x/interpolate(body_stations, 2.12)[0])[2]+.024)
              for x in (.61, .65, .69, .73, .77)], .008, white_led)

    # Wheels are surfaces of revolution about LOCAL X, so hub.rotation_euler.x
    # can be animated directly without corrective rotations or constraints.
    def lathe(label, profile, mat, parent, segments=64):
        rows = []
        for x, radius in profile:
            rows.append([(x, radius*math.cos(math.tau*i/segments),
                          radius*math.sin(math.tau*i/segments))
                         for i in range(segments+1)])
        return grid(label, rows, mat, parent)

    wheels = []
    for axle_name, y in (("Front", 1.39), ("Rear", -1.43)):
        for sign, side in ((-1, "L"), (1, "R")):
            label = axle_name + side
            half_width = .145 if axle_name == "Front" else .165
            hub_x = sign * (.866 if axle_name == "Front" else 1.01)
            hub = empty(label + ".Hub", root, (hub_x, y, .36))
            hub["axle_axis"] = "X"
            hub["radius"] = .36
            wheels.append(hub)
            tire_profile = [
                (-half_width*.91, .254), (-half_width, .278),
                (-half_width, .311), (-half_width*.86, .342),
                (-half_width*.62, .355), (-half_width*.30, .36),
                (half_width*.30, .36), (half_width*.62, .355),
                (half_width*.86, .342), (half_width, .311),
                (half_width, .278), (half_width*.91, .254),
                (-half_width*.91, .254),
            ]
            lathe(label + ".Rubber tire", tire_profile, rubber, hub, 80)
            # Recessed narrow chevron cuts: dark ribbons sit in the tread
            # surface; no raised blocks enlarge the .36 m rolling radius.
            tread_verts, tread_faces = [], []
            for step in range(64):
                a = math.tau*step/64
                for half in (-1, 1):
                    base = len(tread_verts)
                    for x, shift, r in ((0, 0, .3602),
                                        (half*half_width*.50, .035, .358),
                                        (half*half_width*.79, .065, .347)):
                        for da in (-.010, .010):
                            tread_verts.append((x, r*math.cos(a+shift+da),
                                                r*math.sin(a+shift+da)))
                    tread_faces += [(base, base+1, base+3, base+2),
                                    (base+2, base+3, base+5, base+4)]
            mesh(label + ".Directional tread cuts", tread_verts, tread_faces,
                 black, hub, smooth=False)
            outer = sign*(half_width+.001)
            lathe(label + ".Alloy barrel",
                  [(-half_width*.90, .253), (half_width*.90, .253),
                   (half_width*.90, .238), (-half_width*.90, .238),
                   (-half_width*.90, .253)], alloy, hub)
            lathe(label + ".Diamond cut rim lip",
                  [(outer-sign*.016, .247), (outer, .257),
                   (outer+sign*.004, .252), (outer+sign*.004, .239),
                   (outer-sign*.016, .238)], metal, hub)
            for radius in (.282, .315):
                lathe(label + ".Sidewall molded ring %.3f" % radius,
                      [(outer-sign*.005, radius-.002),
                       (outer-sign*.002, radius),
                       (outer-sign*.005, radius+.002)], rubber, hub)
            disc_x = outer-sign*.050
            lathe(label + ".Vented brake disc",
                  [(disc_x, .055), (disc_x, .212),
                   (disc_x-sign*.018, .212), (disc_x-sign*.018, .055),
                   (disc_x, .055)], rotor_mat, hub)
            # Cross-drilled dark discs on the outward rotor face.
            drill_verts, drill_faces = [], []
            for track, radius in enumerate((.147, .182, .201)):
                for k in range(24):
                    a = math.tau*(k+track*.31)/24
                    base = len(drill_verts)
                    for corner in range(8):
                        t = math.tau*corner/8
                        drill_verts.append((disc_x+sign*.0008,
                                            radius*math.cos(a)+.004*math.cos(t),
                                            radius*math.sin(a)+.004*math.sin(t)))
                    drill_faces.append(tuple(base+i for i in range(8)))
            mesh(label + ".Rotor drill pattern", drill_verts, drill_faces,
                 black, hub, smooth=False)
            # Five split Y-spokes are extruded tapered polygons, not cylinders.
            for k in range(5):
                a = math.tau*k/5+.13
                for branch in (-1, 1):
                    outline = [(0.058, a-.12), (.142, a+branch*.12-.052),
                               (.244, a+branch*.19-.032),
                               (.244, a+branch*.19+.032),
                               (.139, a+branch*.12+.052), (.058, a+.12)]
                    polygon = [(outer-sign*(.026*(1-r/.244)),
                                r*math.cos(t), r*math.sin(t)) for r, t in outline]
                    prism(label + ".Split spoke %d %d" % (k, branch),
                          polygon, (-sign*.023, 0, 0), alloy, .004, hub)
            lathe(label + ".Hub cap",
                  [(outer-sign*.023, 0), (outer-sign*.023, .061),
                   (outer+sign*.002, .061), (outer+sign*.007, .047),
                   (outer+sign*.007, 0)], alloy, hub, 40)
            for k in range(5):
                a = math.tau*k/5
                tube(label + ".Lug %d" % k,
                     [(outer+sign*.008, .039*math.cos(a), .039*math.sin(a)),
                      (outer+sign*.017, .039*math.cos(a), .039*math.sin(a))],
                     .008, metal, sides=6, parent=hub)
            # Calipers intentionally do not rotate with the wheel hub.
            x = hub_x+disc_x-sign*.011
            prism(label + ".Fixed brake caliper",
                  [(x, y-.186, .28), (x, y-.216, .33),
                   (x, y-.209, .45), (x, y-.163, .485),
                   (x, y-.130, .435), (x, y-.143, .315)],
                  (sign*.047, 0, 0), caliper_mat, .012)

    root.location = location
    return {"root": root, "wheels": wheels, "radius": 0.36}
