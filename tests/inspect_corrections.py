"""Exercise the geometry defects marked in the user's attempt 18 image."""

import json
import sys
import unittest
from pathlib import Path

import bpy
from mathutils import Vector

arguments=sys.argv[sys.argv.index("--")+1:]
if arguments==["--build-owned"]:
    assert bpy.app.background,"Geometry fixtures require an isolated process"
    root=Path(__file__).resolve().parents[1]
    sys.path.insert(0,str(root/"blender"))
    from hero_car import build_car
    from street import build_street
    config=json.loads((root/"configs/street_scene.json").read_text())
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    bpy.context.scene["task_owner"]=config["run_id"]
    build_street(Path(config["data_root"])/config["run_id"]/"assets/bricks")
    build_car()
else:
    scene_path=Path(arguments[0])
    bpy.ops.wm.open_mainfile(filepath=str(scene_path))
bpy.context.scene.frame_set(1)
bpy.context.view_layer.update()


class CorrectionGeometryTests(unittest.TestCase):
    def test_middle_windows_sit_behind_the_masonry_plane(self):
        fixtures=[
            ((-17.3,91,5),(0,1,0),1,93,1),
            ((7.2,114,5),(0,1,0),1,116,1),
            ((4,118,5),(1,0,0),0,6,1),
            ((-3.5,95,5),(-1,0,0),0,-5.5,-1),
        ]
        graph=bpy.context.evaluated_depsgraph_get()
        for origin,direction,axis,wall,sign in fixtures:
            with self.subTest(origin=origin):
                hit,point,normal,index,obj,matrix=bpy.context.scene.ray_cast(
                    graph,Vector(origin),Vector(direction),distance=4)
                self.assertTrue(hit)
                self.assertEqual(obj.name,"Middle distance windows")
                self.assertGreater(sign*(point[axis]-wall),.05,
                                   "Glazing projects in front of the wall")

    def test_near_sills_touch_the_wall_and_support_the_window(self):
        trim=bpy.data.objects["Sandstone lintels and cornices"]
        for sign,wall in [(1,8.0),(-1,8.15)]:
            with self.subTest(side=sign):
                points=[v.co for v in trim.data.vertices
                        if 7.4<sign*v.co.x<8.5 and abs(v.co.y-6)<.84
                        and 3.8<v.co.z<4.2]
                self.assertTrue(points,"No sill below the selected window")
                self.assertGreaterEqual(max(sign*p.x for p in points),wall+.015,
                                        "Sill floats in front of masonry")
                self.assertGreaterEqual(max(p.z for p in points),4.10,
                                        "Sill does not support the window frame")

    def test_shoulder_slots_do_not_project_above_adjacent_paint(self):
        body=bpy.data.objects["Hero.Continuous sculpted upper body"]
        surfaces=[body]+[obj for obj in bpy.data.objects if "shoulder vent" in obj.name]

        def top_at(x,y):
            heights=[]
            for obj in surfaces:
                hit,point,normal,index=obj.ray_cast(Vector((x,y,2)),Vector((0,0,-1)))
                if hit:
                    heights.append(point.z)
            self.assertTrue(heights)
            return max(heights)

        for x in [-.80,.80]:
            for y in [-1.89+i*.113 for i in range(7)]:
                with self.subTest(x=x,y=y):
                    paint=(top_at(x,y-.043)+top_at(x,y+.043))/2
                    self.assertGreater(paint-top_at(x,y),.007,
                                       "Shoulder slot protrudes or is not recessed")

    def test_arch_trim_overlaps_masonry(self):
        trim=bpy.data.objects["Sandstone lintels and cornices"]
        for sign,wall in [(1,8.0),(-1,8.15)]:
            with self.subTest(side=sign):
                points=[v.co for v in trim.data.vertices
                        if 7.4<sign*v.co.x<8.5 and abs(v.co.y-6)<.86
                        and 6.6<v.co.z<7.0]
                self.assertTrue(points)
                self.assertGreaterEqual(max(sign*p.x for p in points),wall+.015)


suite=unittest.defaultTestLoader.loadTestsFromTestCase(CorrectionGeometryTests)
result=unittest.TextTestRunner(verbosity=2).run(suite)
if not result.wasSuccessful():
    raise RuntimeError("Annotated geometry defects remain")
