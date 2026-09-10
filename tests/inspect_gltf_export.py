"""Run separately in supervised Blender; never part of ordinary discovery."""

import argparse
import math
import sys
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "blender"))
from pipeline.evidence import atomic_json


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
    return {"fixture": "signed-planar-and-normal", "complete": True}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", action="store_true")
    parser.add_argument("--receipt", required=True)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
    assert bpy.app.background
    if not args.fixture:
        raise ValueError("Select an inspection mode")
    atomic_json(args.receipt, material_fixture())
    print("GLTF_INSPECTION_COMPLETE")
