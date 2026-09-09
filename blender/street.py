"""Original modular street geometry, in meters with forward along positive Y."""

import math
import random
from pathlib import Path

import bpy
from mathutils import Vector


def material(name, color, roughness=.6, metallic=0):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (*color, 1)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*color, 1)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    return mat


def image_surface(name, texture_root, asset, meters, color, bump_distance):
    mat = material(name, color, .83)
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    pos = nodes.new("ShaderNodeNewGeometry")
    scale=nodes.new("ShaderNodeVectorMath")
    scale.operation="SCALE"
    scale.inputs["Scale"].default_value=1/meters
    links.new(pos.outputs["Position"],scale.inputs[0])
    textures={}
    for channel in ["Color","Roughness","Displacement"]:
        image_path=Path(texture_root)/f"{asset}_1K-JPG_{channel}.jpg"
        if not image_path.is_file():
            raise FileNotFoundError(image_path)
        texture=nodes.new("ShaderNodeTexImage")
        texture.projection="BOX"
        texture.projection_blend=.05
        texture.image=bpy.data.images.load(str(image_path),check_existing=True)
        texture.image.colorspace_settings.name="sRGB" if channel=="Color" else "Non-Color"
        texture.image.pack()
        links.new(scale.outputs[0],texture.inputs["Vector"])
        textures[channel]=texture
    tint=nodes.new("ShaderNodeMixRGB")
    tint.blend_type="MULTIPLY"
    tint.inputs[0].default_value=1
    tint.inputs[2].default_value=(*color,1)
    links.new(textures["Color"].outputs["Color"],tint.inputs[1])
    links.new(tint.outputs[0],nodes.get("Principled BSDF").inputs["Base Color"])
    links.new(textures["Roughness"].outputs["Color"],nodes.get("Principled BSDF").inputs["Roughness"])
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = .38
    bump.inputs["Distance"].default_value = bump_distance
    links.new(textures["Displacement"].outputs["Color"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], nodes.get("Principled BSDF").inputs["Normal"])
    return mat


def masonry(name, color, texture_root):
    tint=(.7+color[0]*.3,.45+color[1],.4+color[2])
    return image_surface(name,texture_root,"Bricks059",1.05,tint,.028)


class Geometry:
    """Batch static geometry by material to keep scene evaluation inexpensive."""

    def __init__(self, name, mat):
        self.name, self.mat = name, mat
        self.vertices, self.faces = [], []

    def box(self, center, size):
        x, y, z = center
        a, b, c = (v / 2 for v in size)
        start = len(self.vertices)
        self.vertices.extend((x + i*a, y + j*b, z + k*c)
                             for i, j, k in [(-1,-1,-1),(-1,-1,1),(-1,1,-1),(-1,1,1),
                                             (1,-1,-1),(1,-1,1),(1,1,-1),(1,1,1)])
        self.faces.extend(tuple(start + i for i in reversed(face))
                          for face in [(0,4,6,2),(1,3,7,5),(0,1,5,4),
                                       (2,6,7,3),(0,2,3,1),(4,5,7,6)])

    def rod(self, a, b, radius=.025, sides=8):
        a, b = Vector(a), Vector(b)
        direction = (b - a).normalized()
        other = Vector((0, 0, 1)) if abs(direction.z) < .9 else Vector((1, 0, 0))
        u = direction.cross(other).normalized() * radius
        v = direction.cross(u).normalized() * radius
        start = len(self.vertices)
        for point in [a, b]:
            for i in range(sides):
                angle = i * 2 * math.pi / sides
                self.vertices.append(tuple(point + u*math.cos(angle) + v*math.sin(angle)))
        self.faces.append(tuple(start+i for i in reversed(range(sides))))
        self.faces.append(tuple(start+sides+i for i in range(sides)))
        for i in range(sides):
            j = (i + 1) % sides
            self.faces.append((start+i, start+j, start+sides+j, start+sides+i))

    def finish(self, bevel=0):
        mesh = bpy.data.meshes.new(self.name)
        mesh.from_pydata(self.vertices, [], self.faces)
        mesh.materials.append(self.mat)
        mesh.update()
        obj = bpy.data.objects.new(self.name, mesh)
        bpy.context.collection.objects.link(obj)
        if bevel:
            mod = obj.modifiers.new("Masonry edge radius", "BEVEL")
            mod.width, mod.segments = bevel, 2
        return obj


def facade_shell(wall, side, y, height, near):
    wall.box((side*10.65,y,height/2),(4.7,7.97,height))
    wall.box((side*8.14,y,.2),(.28,7.97,.4))
    floors=5 if near else int(height/3.2)
    width=1.35 if near else 1.12
    window_height=2.17 if near else 1.6
    for edge in [-3.86,3.86]:
        wall.box((side*8.14,y+edge,height/2),(.28,.25,height))
    for bay in [-2.5,0,2.5]:
        for floor in range(floors):
            z=2+floor*3.2
            low=floor*3.2+.4
            high=min(height,(floor+1)*3.2+.4)
            for sign in [-1,1]:
                wall.box((side*8.14,y+bay+sign*(width/2+(2.5-width)/4),(low+high)/2),
                         (.28,(2.5-width)/2,high-low))
            bottom=z-window_height/2
            wall.box((side*8.14,y+bay,(low+bottom)/2),(.28,width,bottom-low))
            top=z+window_height/2
            # Separate masonry strips leave a real opening around each arch.
            strips=24 if near and floor in [1,4] else 1
            for strip in range(strips):
                u=-1+(strip+.5)*2/strips
                arch=.5*math.sqrt(max(0,1-u*u)) if strips>1 else 0
                start=top+arch
                wall.box((side*8.14,y+bay+u*width/2,(start+high)/2),
                         (.28,width/strips,high-start))
    top=floors*3.2+.4
    if height>top:
        wall.box((side*8.14,y,(top+height)/2),(.28,7.97,height-top))


def recessed_window_wall(wall, glass, frames, trim, origin, across, inward,
                        length, height, centers, width, entry=None):
    origin,across,inward=Vector(origin),Vector(across),Vector(inward)

    def box(group,u,d,z,w,thickness,h):
        center=origin+across*u+inward*d+Vector((0,0,z))
        size=(abs(across.x)*w+abs(inward.x)*thickness,
              abs(across.y)*w+abs(inward.y)*thickness,h)
        group.box(center,size)

    edge=0
    for column,u in enumerate(centers):
        left,right=u-width/2,u+width/2
        box(wall,(edge+left)/2,.18,height/2,left-edge,.36,height)
        bottom_edge=0
        for row,z in enumerate(range(2,height,3)):
            bottom=.25 if row==0 and column==entry else z-.94
            top=z+.94
            box(wall,u,.18,(bottom_edge+bottom)/2,width,.36,bottom-bottom_edge)
            box(glass,u,.19,(bottom+top)/2,width,.05,top-bottom)
            for offset in [-width/2+.025,width/2-.025]:
                box(frames,u+offset,.12,(bottom+top)/2,.05,.10,top-bottom)
            for rail in [bottom+.025,z+.18,top-.025]:
                box(frames,u,.12,rail,width,.10,.05)
            box(trim,u,.05,bottom-.055,width+.20,.50,.15)
            box(trim,u,.10,top+.075,width+.16,.32,.18)
            bottom_edge=top
        if height>bottom_edge:
            box(wall,u,.18,(bottom_edge+height)/2,width,.36,height-bottom_edge)
        edge=right
    box(wall,(edge+length)/2,.18,height/2,length-edge,.36,height)
    for z in range(3,height,3):
        box(trim,length/2,.035,z+.25,length+.08,.18,.10)
    box(trim,length/2,.025,.15,length,.22,.30)


def build_street(texture_root):
    random.seed(29)
    iron_mat = material("Painted iron", (.023, .03, .028), .54, .65)
    iron = Geometry("Fire escapes and railings", iron_mat)
    trim = Geometry("Sandstone lintels and cornices",
                    material("Warm limestone", (.26, .19, .135), .73))
    frames = Geometry("Window sashes", material("Painted window frames", (.34,.29,.22), .55))
    glass = Geometry("Recessed window glass", material("Dark reflected glass", (.025,.043,.06), .18, .35))
    doors = Geometry("Recessed shopfronts", material("Storefront paint", (.052,.039,.032), .63))
    plaster = Geometry("Ground floor plaster", material("Aged gray plaster", (.33,.34,.335), .9))
    shopred = Geometry("Shopfront red pilasters", material("Oxide shop paint", (.20,.019,.016), .62))
    sidewalks = Geometry("Sidewalk slabs", material("Concrete", (.24,.26,.28), .9))
    curb = Geometry("Curbstones", material("Curb stone", (.24,.26,.28), .87))
    colors = [(.36,.12,.067),(.29,.077,.037),(.42,.175,.09),(.25,.10,.06),(.32,.17,.095)]
    bricks = [Geometry(f"Brick facades {i}", masonry(f"Brick {i}", color,texture_root)) for i,color in enumerate(colors)]

    road_mat = image_surface("Fine asphalt",Path(texture_root).parent/"asphalt",
                             "Asphalt012",1.5,(1,.95,1),.006)
    road = Geometry("Continuous asphalt roadway", road_mat)
    road.box((0,160,-.125),(16,440,.25))
    road.box((0,62,-.125),(120,12,.25))
    road.finish()
    for side in [-1, 1]:
        for y in range(-40, 171, 2):
            if 56 <= y <= 68:
                continue
            sidewalks.box((side*7,y,.02),(1.96,1.985,.22))
            curb.box((side*6.02,y,.015),(.16,1.98,.25))
        for index in range(12):
            if index == 10:
                continue
            module_groups=bricks+[frames,glass,doors,plaster,shopred,iron,trim]
            starts=[(group,len(group.vertices)) for group in module_groups]
            y = -18 + index*8
            near = index < 9
            height = 18.9 + (index % 3)*1.4 if near else 12.8+(index%4)*2.1
            wall = bricks[(index + (side == 1)) % len(bricks)]
            facade_shell(wall,side,y,height,near)
            trim.box((side*7.91,y,.48),(.19,7.97,.75))
            bands=[3.7,height-.65,height-.3,height] if near else [3.7,height]
            for z in bands:
                trim.box((side*7.79,y,z),(.48,8.06,.16 if z<height else .28))
            if near:
                for yy in [y-3.85,y+3.85]:
                    trim.box((side*7.97,yy,9.1),(.15,.24,10.1))
            for floor in range(5 if near else int(height/3.2)):
                z = 2 + floor*3.2
                for bay in [-2.5,0,2.5]:
                    yy = y+bay
                    window_width=1.35 if near else 1.12
                    window_height=2.17 if near else 1.6
                    glass.box((side*8.12, yy, z),(.065,window_width,window_height))
                    if near and floor in [1,4]:
                        base=len(glass.vertices)
                        arch=[(side*8.10,yy,z+window_height/2)]
                        arch.extend((side*8.10,yy+window_width/2*math.cos(a),
                                     z+window_height/2+.5*math.sin(a))
                                    for a in [math.pi*i/24 for i in range(25)])
                        glass.vertices.extend(arch)
                        face=tuple(range(base,base+len(arch)))
                        glass.faces.append(tuple(reversed(face)) if side>0 else face)
                    edge=window_width/2+.025
                    for offset in [-edge,edge]:
                        frames.box((side*7.97,yy+offset,z),(.08,.03,window_height+.05))
                    crossbars=[z-window_height/2,z,z+window_height/2] if near else [z-window_height/2,z+window_height/2]
                    for zz in crossbars:
                        frames.box((side*7.965,yy,zz),(.09,window_width+.09,.055))
                    if near:
                        trim.box((side*7.99,yy,z-window_height/2-.04),(.48,1.6,.14))
                        if floor not in [1,4]:
                            trim.box((side*7.99,yy,z+window_height/2+.07),(.30,1.6,.18))
                    if floor in [1,4] and near:
                        # Segmented arch surrounds keep an editable masonry profile.
                        for k in range(12):
                            a=math.pi*k/12
                            b=math.pi*(k+1)/12
                            stone_x=side*8.02
                            trim.rod((stone_x,yy+.735*math.cos(a),z+1.10+.5*math.sin(a)),
                                     (stone_x,yy+.735*math.cos(b),z+1.10+.5*math.sin(b)), .07)
                        for offset in [-.735,.735]:
                            trim.box((side*8.03,yy+offset,z),(.28,.12,window_height))
            # Stoops and a dark doorway establish ground floor scale.
            doors.box((side*7.73,y,1.35),(.09,1.25,2.55))
            if side == -1 and index in [1,2,4]:
                plaster.box((-7.76,y,1.82),(.14,7.85,3.6))
                for yy in [y-2.5,y,y+2.5]:
                    glass.box((-7.66,yy,1.9),(.06,1.5,2.65))
                    for edge in [-.8,.8]:
                        shopred.box((-7.61,yy+edge,1.9),(.13,.16,2.9))
                    shopred.box((-7.6,yy,3.28),(.14,1.8,.17))
                if index == 2:
                    bpy.ops.object.text_add(location=(-7.48,y,3.05),
                                            rotation=(math.pi/2,0,math.pi/2))
                    sign=bpy.context.object
                    sign.name="Original market sign"
                    sign.data.body="MARKET"
                    sign.data.align_x="CENTER"
                    sign.data.size=.25
                    sign.data.extrude=.005
                    sign.data.materials.append(material("Sign lettering",(.64,.59,.39),.4))
            if near:
                iron.rod((side*7.77,y+3.7,.2),(side*7.77,y+3.7,height),.035)
                for low,high in [(-3.8,-1.2),(1.2,3.8)]:
                    for z in [.3,1.0]:
                        iron.rod((side*6.8,y+low,z),(side*6.8,y+high,z),.024)
                    for j in range(14):
                        yy=y+low+(high-low)*j/13
                        iron.rod((side*6.8,yy,.2),(side*6.8,yy,1.07),.013)
            for step in range(4):
                trim.box((side*(7.6-step*.23),y,.13+step*.11),(.35,1.9,.25+step*.22))
            for yy in [y-1,y+1]:
                iron.rod((side*6.8,yy,.8),(side*7.8,yy,1.7),.04)
                for x,z in [(6.85,.85),(7.35,1.3)]:
                    iron.rod((side*x,yy,.2),(side*x,yy,z),.025)
            # Four escape platforms and alternating stair flights per facade.
            if near:
                for level in range(1,5):
                    z=.8+level*3.2
                    for xx in [6.87,7.81]:
                        iron.box((side*xx,y,z),(.07,3.8,.1))
                    for slat in range(26):
                        iron.box((side*7.35,y-1.9+slat*.15,z),(.95,.035,.065))
                    for yy in [y-1.9,y+1.9]:
                        iron.rod((side*6.86,yy,z),(side*6.86,yy,z+1.05),.025)
                        iron.rod((side*6.86,yy,z+1.05),(side*7.86,yy,z+1.05),.025)
                    for j in range(20):
                        yy=y-1.9+j*.2
                        iron.rod((side*6.86,yy,z),(side*6.86,yy,z+1.05),.012)
                    iron.rod((side*6.86,y-1.9,z+1.05),(side*6.86,y+1.9,z+1.05),.029)
                    direction=1 if level%2 else -1
                    for j in range(17):
                        t=j/16
                        yy=y+direction*(-1.55+3.1*t)
                        zz=z-3.2*t
                        iron.box((side*7.35,yy,zz),(.78,.22,.06))
                    for xx in [6.96,7.75]:
                        for dz in [0,.85]:
                            iron.rod((side*xx,y-direction*1.55,z+dz),
                                     (side*xx,y+direction*1.55,z-3.2+dz),.022)
                        for j in range(9):
                            t=j/8
                            yy=y+direction*(-1.55+3.1*t)
                            zz=z-3.2*t
                            iron.rod((side*xx,yy,zz),(side*xx,yy,zz+.85),.017)
            # Move each complete module so windows, stairs and walls stay aligned.
            setback=[0,.35,-.25,.15][(index+(side==1))%4]
            for group,start in starts:
                group.vertices[start:]=[(x+side*setback,yv,zv)
                                        for x,yv,zv in group.vertices[start:]]
            if side==-1 and index==2:
                sign.location.x-=setback
    for item in bricks+[frames,glass,doors,plaster,shopred,iron,sidewalks,curb,trim]:
        item.finish(.008 if item is trim else 0)
    # Buildings beyond the cross street close the view instead of an empty horizon.
    skyline = Geometry("Distant skyline", material("Distant stone", (.31,.36,.4), .8))
    skyglass = Geometry("Distant glazing", material("Distant blue glass", (.15,.23,.3), .24, .35))
    midrise=Geometry("Middle distance masonry",masonry("Middle distance brick",(.26,.12,.075),texture_root))
    midtrim=Geometry("Middle distance concrete",material("Middle distance concrete",(.38,.37,.34),.8))
    midglass=Geometry("Middle distance windows",material("Middle distance window glass",(.025,.04,.05),.25,.3))
    midframes=Geometry("Middle distance window frames",material("Middle distance painted frames",(.15,.13,.10),.45))
    for x,y,h,width,depth in [(-12,102,12,13,18),(13,126,16,14,20),(-17,157,19,12,22)]:
        front=y-depth/2
        sign=math.copysign(1,x)
        inner=x-sign*width/2
        # The opaque interior starts behind both recessed window planes.
        midrise.box((x+sign*.19,y+.19,h/2),(width-.38,depth-.38,h))
        columns=[1.2+i*2.1 for i in range(int(width/2.1))]
        recessed_window_wall(midrise,midglass,midframes,midtrim,
                             (x-width/2,front,0),(1,0,0),(0,1,0),
                             width,h,columns,1.24,entry=len(columns)//2)
        recessed_window_wall(midrise,midglass,midframes,midtrim,
                             (inner,front,0),(0,1,0),(sign,0,0),
                             depth,h,list(range(2,int(depth),3)),1.5)
        for z,overhang,thickness in [(h-.2,.12,.14),(h,.36,.24),(h+.22,.20,.12)]:
            midtrim.box((x,y,z),(width+overhang,depth+overhang,thickness))
        midrise.box((x+sign*width*.22,y+depth*.2,h+.55),(1.15,1.5,1.1))
        midtrim.box((x+sign*width*.22,y+depth*.2,h+1.12),(1.3,1.65,.16))
    midrise.finish()
    midtrim.finish(.012)
    midglass.finish()
    midframes.finish()
    tower=Geometry("Curved glass office tower",material("Office tower glazing",(.12,.22,.30),.2,.6))
    tower.rod((8,195,0),(8,195,22),6,48)
    for j in range(48):
        a=j*math.tau/48
        b=(j+1)*math.tau/48
        x,y=8+6.04*math.cos(a),195+6.04*math.sin(a)
        skyline.rod((x,y,0),(x,y,22),.065,6)
        for z in range(1,23):
            skyline.rod((x,y,z),(8+6.04*math.cos(b),195+6.04*math.sin(b),z),.04,6)
    tower.finish()
    for x,y,h,width in [(-15,280,28,13),(0,250,22,16),(16,305,34,13)]:
        skyline.box((x,y,h/2),(width,10,h))
        for row in range(1,int(h/1.5)):
            z=row*1.5
            for column in range(int(width/1.2)):
                dx=-width/2+.65+column*1.2
                skyglass.box((x+dx,y-5.03,z),(.78,.05,1.02))
    skyline.finish()
    skyglass.finish()
    bark=Geometry("Street tree branches",material("Tree bark",(.09,.055,.025),.95))
    leaves=[Geometry(f"Street tree leaves {i}",material(f"Leaf color {i}",color,.85))
            for i,color in enumerate([(.045,.065,.027),(.07,.078,.035),(.095,.08,.035)])]
    for yy in [28,57]:
        origin=Vector((-7.15,yy,.15))
        bark.rod(origin,origin+Vector((.1,0,2.5)),.07,10)
        for branch in range(9):
            angle=branch*2.4
            end=origin+Vector((math.cos(angle)*1.0,math.sin(angle)*1.1,2.7+random.random()*1.2))
            bark.rod(origin+Vector((.1,0,2.0)),end,.025,7)
            for k in range(12):
                pos=end+Vector((random.uniform(-.5,.5),random.uniform(-.5,.5),random.uniform(-.4,.4)))
                bark.rod(end,pos,.005,5)
                for j in range(45):
                    center=pos+Vector((random.uniform(-.22,.22),random.uniform(-.22,.22),random.uniform(-.2,.2)))
                    a=random.random()*math.tau
                    u=Vector((math.cos(a),math.sin(a),random.uniform(-.5,.5)))*.055
                    v=Vector((-math.sin(a),math.cos(a),random.uniform(-.5,.5)))*.022
                    leaf=leaves[random.randrange(len(leaves))]
                    start=len(leaf.vertices)
                    leaf.vertices.extend(tuple(p) for p in [center-u,center-v,center+u,center+v])
                    leaf.faces.append(tuple(start+i for i in range(4)))
    bark.finish()
    for leaf in leaves:
        leaf.finish()
