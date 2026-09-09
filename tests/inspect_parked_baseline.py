"""Verify the rollback preserves the original vehicle geometry exactly."""

import hashlib
import importlib.util
import sys
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path

import bpy

assert bpy.app.background
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"blender"))
from parked_cars import build_parked

baseline=Path(sys.argv[sys.argv.index("--")+1])
loader=SourceFileLoader("baseline_parked",str(baseline))
spec=importlib.util.spec_from_loader(loader.name,loader)
module=importlib.util.module_from_spec(spec)
loader.exec_module(module)
original=module.build_parked("Original","minivan")
restored=build_parked("Restored","minivan")


class BodyRestorationTests(unittest.TestCase):
    def test_original_body_and_glazing_geometry_is_preserved(self):
        for source in original.children:
            if source.type!="MESH":
                continue
            key=source.name.split(" | ")[1]
            target=bpy.data.objects["Restored | "+key]
            with self.subTest(part=key):
                for field in ["vertices","faces","smoothing"]:
                    signatures=[]
                    for obj in [source,target]:
                        values=([tuple(v.co) for v in obj.data.vertices] if field=="vertices"
                                else [tuple(p.vertices) for p in obj.data.polygons] if field=="faces"
                                else [p.use_smooth for p in obj.data.polygons])
                        signatures.append(hashlib.sha256(repr(values).encode()).hexdigest())
                    self.assertEqual(*signatures,msg=f"{key}: {field} differs from the original")

    def test_plate_text_and_glossier_paint_remain(self):
        text=bpy.data.objects["Restored | plate text"]
        self.assertEqual(text.data.body,"SCN 018")
        self.assertEqual(text.parent,restored)
        shader=bpy.data.materials["Restored | enamel"].node_tree.nodes["Principled BSDF"]
        previous=bpy.data.materials["Original | enamel"].node_tree.nodes["Principled BSDF"]
        self.assertLess(shader.inputs["Roughness"].default_value,
                        previous.inputs["Roughness"].default_value)


result=unittest.TextTestRunner(verbosity=2).run(
    unittest.defaultTestLoader.loadTestsFromTestCase(BodyRestorationTests))
if not result.wasSuccessful():
    raise RuntimeError("Original minivan geometry has not been restored")
