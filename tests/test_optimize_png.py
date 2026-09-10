import io
import struct
import unittest

from PIL import Image, PngImagePlugin

from tools.optimize_png import optimize_png


class OptimizePngTests(unittest.TestCase):
    def encode(self, image, info=None):
        output = io.BytesIO()
        image.save(output, format="PNG", compress_level=0, pnginfo=info)
        return output.getvalue()

    def test_exact_palette_keeps_every_pixel_and_dimensions(self):
        image = Image.new("RGB", (128, 128))
        image.putdata([(index % 39, 40, 70) for index in range(128 * 128)])
        original = self.encode(image)
        optimized = optimize_png(original)
        result = Image.open(io.BytesIO(optimized))
        self.assertLess(len(optimized), len(original) // 4)
        self.assertEqual(result.size, (128, 128))
        self.assertEqual(result.convert("RGBA").tobytes(), image.convert("RGBA").tobytes())

    def test_preserves_color_space_but_removes_descriptive_metadata(self):
        info = PngImagePlugin.PngInfo()
        info.add(b"sRGB", b"\x03")
        info.add(b"gAMA", struct.pack(">I", 45455))
        info.add_text("Comment", "diagnostic only")
        original = self.encode(Image.new("RGB", (32, 32), (12, 40, 80)), info)
        decoded = Image.open(io.BytesIO(optimize_png(original)))
        self.assertEqual(decoded.info["srgb"], 3)
        self.assertEqual(decoded.info["gamma"], 0.45455)
        self.assertNotIn("Comment", decoded.info)

    def test_full_color_alpha_image_is_not_quantized(self):
        image = Image.new("RGBA", (64, 64))
        image.putdata([(i % 256, i // 256, 79, i % 127) for i in range(4096)])
        result = Image.open(io.BytesIO(optimize_png(self.encode(image))))
        self.assertEqual(result.convert("RGBA").tobytes(), image.tobytes())

    def test_removes_exif_from_non_palette_output(self):
        image = Image.new("RGBA", (64, 64))
        image.putdata([(i % 256, i // 256, 79, i % 127) for i in range(4096)])
        exif = Image.Exif()
        exif[0x0131] = "diagnostic renderer"
        output = io.BytesIO()
        image.save(output, format="PNG", exif=exif)
        result = Image.open(io.BytesIO(optimize_png(output.getvalue())))
        self.assertNotIn("exif", result.info)
        self.assertEqual(result.tobytes(), image.tobytes())

    def test_rejects_non_png_and_oversize_images(self):
        with self.assertRaises(ValueError):
            optimize_png(b"not png")
        with self.assertRaisesRegex(ValueError, "dimensions"):
            optimize_png(self.encode(Image.new("RGB", (4097, 1))))

    def test_rejects_unreviewed_embedded_color_profiles(self):
        output = io.BytesIO()
        Image.new("RGB", (8, 8)).save(output, format="PNG", icc_profile=b"unreviewed profile")
        self.assertEqual(Image.open(io.BytesIO(output.getvalue())).info["icc_profile"], b"unreviewed profile")
        with self.assertRaisesRegex(ValueError, "profile"):
            optimize_png(output.getvalue())


if __name__ == "__main__":
    unittest.main()
