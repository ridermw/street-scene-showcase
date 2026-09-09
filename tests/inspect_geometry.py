"""Check surface orientation in Blender before lighting comparisons."""

import sys
from pathlib import Path

import bmesh

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"blender"))
from street import Geometry, material

geometry=Geometry("Orientation fixture",material("Fixture",(0.5,0.5,0.5)))
geometry.box((0,0,0),(2,3,4))
obj=geometry.finish()
mesh=bmesh.new()
mesh.from_mesh(obj.data)
volume=mesh.calc_volume(signed=True)
mesh.free()
assert abs(volume-24)<1e-6, f"Box normals face inward: signed volume {volume}"
print("Box surface orientation is outward")
