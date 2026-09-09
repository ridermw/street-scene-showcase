import importlib.util
import tempfile
import unittest
from pathlib import Path

from PIL import Image


class PacketTests(unittest.TestCase):
    def module(self):
        path=Path(__file__).resolve().parents[1]/"tools/label_packet.py"
        self.assertTrue(path.exists(),"Labeled critic packet is not implemented")
        spec=importlib.util.spec_from_file_location("packet",path)
        module=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_packet_preserves_image_and_adds_neutral_label_band(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            source=root/"source.png"
            Image.new("RGB",(100,100),"red").save(source)
            self.module().make_packet({"A":source},root/"packet")
            with Image.open(root/"packet/A.jpg") as image:
                self.assertEqual(image.size,(100,156))
                self.assertGreater(image.getpixel((50,100))[0],240)
                self.assertLess(image.getpixel((50,100))[1],10)
                self.assertNotIn("exif",image.info)
            self.assertTrue((root/"packet-manifest.json").is_file())

    def test_mismatched_sizes_and_unsafe_labels_are_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            for name,size in [("one",(100,100)),("two",(200,100))]:
                Image.new("RGB",size).save(root/f"{name}.png")
            for sources in [{"A":root/"one.png","B":root/"two.png"},
                            {"../escape":root/"one.png"}]:
                with self.assertRaises(ValueError):
                    self.module().make_packet(sources,root/"packet")
                self.assertFalse((root/"packet").exists())
