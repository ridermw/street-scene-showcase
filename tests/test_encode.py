import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path


class EncodingTests(unittest.TestCase):
    def encoder(self):
        path=Path(__file__).resolve().parents[1]/"tools/encode_video.py"
        self.assertTrue(path.exists(), "Video encoder is not implemented")
        spec=importlib.util.spec_from_file_location("encoder",path)
        module=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_missing_frame_cannot_create_video(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)
            with self.assertRaises(ValueError):
                self.encoder().encode(path, path/"out.mp4", [],1,2,"scene",32,32)
            self.assertFalse((path/"out.mp4").exists())

    def test_real_sequence_encodes_at_requested_rate_and_size(self):
        encoder=self.encoder()
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)
            subprocess.run(["ffmpeg","-v","error","-f","lavfi","-i",
                            "color=c=red:s=32x32:r=24","-frames:v","2",
                            str(path/"%04d.png")],check=True)
            rows=[{"frame":i,"fingerprint":"scene","sha256":encoder.digest(path/f"{i:04d}.png")}
                  for i in [1,2]]
            result=encoder.encode(path,path/"out.mp4",rows,1,2,"scene",32,32)
            self.assertEqual((result["width"],result["height"]),(32,32))
            self.assertEqual(result["r_frame_rate"],"24/1")
            self.assertEqual(int(result["nb_read_frames"]),2)

    def test_changed_frame_is_rejected_before_encoding(self):
        encoder=self.encoder()
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)
            (path/"0001.png").write_bytes(b"changed")
            rows=[{"frame":1,"fingerprint":"scene","sha256":"old"}]
            with self.assertRaisesRegex(ValueError,"hash"):
                encoder.encode(path,path/"out.mp4",rows,1,1,"scene",32,32)


if __name__=="__main__":
    unittest.main()
