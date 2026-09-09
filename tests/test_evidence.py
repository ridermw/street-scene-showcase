import importlib.util
import tempfile
import unittest
from pathlib import Path


class EvidenceTests(unittest.TestCase):
    def evidence(self):
        path = Path(__file__).resolve().parents[1] / "pipeline/evidence.py"
        self.assertTrue(path.exists(), "Evidence validation is not implemented")
        spec = importlib.util.spec_from_file_location("evidence", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_dependency_change_invalidates_capture(self):
        ev = self.evidence()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "texture"
            path.write_bytes(b"old")
            fingerprint = ev.fingerprint([path], {"samples": 64})
            path.write_bytes(b"new")
            self.assertNotEqual(fingerprint, ev.fingerprint([path], {"samples": 64}))

    def test_missing_dependencies_are_not_success(self):
        with self.assertRaises(FileNotFoundError):
            self.evidence().fingerprint([Path("/not/a/real/file")], {})

    def test_review_rejects_stale_or_missing_images(self):
        ev = self.evidence()
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / "image.png"
            image.write_bytes(b"pixels")
            review = {"image_hashes": {str(image): ev.digest(image)},
                      "scene_fingerprint": "scene", "reference_fingerprint": "ref",
                      "instructions_version": "v1", "decision": "reject"}
            ev.validate_review(review, "scene", "ref", "v1")
            image.write_bytes(b"new pixels")
            with self.assertRaisesRegex(ValueError, "image"):
                ev.validate_review(review, "scene", "ref", "v1")
            with self.assertRaisesRegex(ValueError, "fingerprint"):
                ev.validate_review(review, "different", "ref", "v1")
            review["image_hashes"] = {}
            with self.assertRaises(ValueError):
                ev.validate_review(review, "scene", "ref", "v1")

    def test_frame_sequence_rejects_gaps_and_mixed_specification(self):
        ev = self.evidence()
        frames = [{"frame": i, "fingerprint": "a"} for i in range(1, 4)]
        ev.validate_sequence(frames, 1, 3, "a")
        for bad in [frames[:2], frames + [frames[0]],
                    [{"frame": 1, "fingerprint": "b"}] + frames[1:],
                    list(reversed(frames))]:
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    ev.validate_sequence(bad, 1, 3, "a")

    def test_progress_escapes_text_and_blocks_path_traversal(self):
        ev = self.evidence()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / "image.png"
            image.write_bytes(b"image")
            ev.write_progress(root, "<script>bad</script>", [image], "correcting")
            html = (root / "index.html").read_text()
            self.assertNotIn("<script>bad", html)
            self.assertIn("&lt;script&gt;", html)
            with self.assertRaises(ValueError):
                ev.write_progress(root, "bad", [root / "../secret.png"], "running")
            self.assertEqual((root / "index.html").read_text(), html)

    def test_atomic_record_never_replaces_valid_data_on_invalid_input(self):
        ev = self.evidence()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "record.json"
            ev.atomic_json(path, {"state": "complete"})
            original = path.read_bytes()
            with self.assertRaises(TypeError):
                ev.atomic_json(path, {"invalid": object()})
            self.assertEqual(path.read_bytes(), original)

    def test_retained_dependency_survives_source_change(self):
        ev = self.evidence()
        self.assertTrue(hasattr(ev, "retain_dependencies"), "Dependency retention is not implemented")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.py"
            source.write_text("original")
            retained = ev.retain_dependencies([source], root / "retained")
            source.write_text("changed")
            self.assertEqual(Path(retained[str(source)]["path"]).read_text(), "original")
            self.assertNotEqual(retained[str(source)]["sha256"], ev.digest(source))

    def test_progress_displays_only_local_motion_video(self):
        ev=self.evidence()
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            video=root/"motion.mp4"
            video.write_bytes(b"fixture")
            ev.write_progress(root,"Motion sample",[],"reviewing",videos=[video])
            self.assertIn('<video controls', (root/"index.html").read_text())
            with self.assertRaises(ValueError):
                ev.write_progress(root,"Blocked",[],"reviewing",videos=[root/"../outside.mp4"])


if __name__ == "__main__":
    unittest.main()
