import importlib.util
import tempfile
import unittest
from pathlib import Path


class RuntimeTests(unittest.TestCase):
    def runtime(self):
        path = Path(__file__).resolve().parents[1] / "pipeline" / "runtime.py"
        self.assertTrue(path.exists(), "Runtime resource guard is not implemented")
        spec = importlib.util.spec_from_file_location("runtime", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_refuses_job_that_consumes_recovery_reserve(self):
        rt = self.runtime()
        with self.assertRaisesRegex(RuntimeError, "deadline"):
            rt.check_capacity(now=90, deadline=100, estimate_seconds=6,
                              reserve_seconds=5, free_bytes=200,
                              min_free_bytes=100, used_bytes=0,
                              max_bytes=100, estimate_bytes=1)

    def test_refuses_low_disk_and_excess_growth(self):
        rt = self.runtime()
        for free, used in [(100, 0), (500, 100)]:
            with self.subTest(free=free, used=used):
                with self.assertRaisesRegex(RuntimeError, "storage"):
                    rt.check_capacity(now=0, deadline=100, estimate_seconds=1,
                                      reserve_seconds=5, free_bytes=free,
                                      min_free_bytes=100, used_bytes=used,
                                      max_bytes=100, estimate_bytes=1)

    def test_accepts_exact_resource_boundary(self):
        self.runtime().check_capacity(
            now=0, deadline=10, estimate_seconds=5, reserve_seconds=5,
            free_bytes=110, min_free_bytes=100, used_bytes=90,
            max_bytes=100, estimate_bytes=10)

    def test_serializes_heavy_jobs_and_releases_after_error(self):
        rt = self.runtime()
        with tempfile.TemporaryDirectory() as directory:
            lock = Path(directory) / "heavy.lock"
            with self.assertRaisesRegex(ValueError, "fixture"):
                with rt.heavy_lock(lock):
                    with self.assertRaisesRegex(RuntimeError, "heavy job"):
                        with rt.heavy_lock(lock):
                            self.fail("Concurrent heavy job started")
                    raise ValueError("fixture")
            with rt.heavy_lock(lock):
                self.assertTrue(lock.exists())


if __name__ == "__main__":
    unittest.main()
