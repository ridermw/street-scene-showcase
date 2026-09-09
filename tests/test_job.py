import importlib.util
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class JobTests(unittest.TestCase):
    def job(self):
        path = Path(__file__).resolve().parents[1] / "pipeline/job.py"
        self.assertTrue(path.exists(), "Owned process runner is not implemented")
        spec = importlib.util.spec_from_file_location("job", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_nonzero_exit_is_a_failure(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(RuntimeError, "exit"):
                self.job().run_owned([sys.executable, "-c", "raise SystemExit(7)"],
                                     Path(d), time.time() + 10, min_free=0, max_bytes=100000)

    def test_deadline_cancels_owned_process(self):
        with tempfile.TemporaryDirectory() as d:
            start = time.monotonic()
            with self.assertRaisesRegex(RuntimeError, "deadline"):
                self.job().run_owned([sys.executable, "-c", "import time; time.sleep(60)"],
                                     Path(d), time.time() + .3, min_free=0, max_bytes=100000)
            self.assertLess(time.monotonic() - start, 5)

    def test_growth_limit_stops_child_and_preserves_output(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "output"
            code = f"from pathlib import Path; import time; Path({str(path)!r}).write_bytes(b'x'*1000); time.sleep(60)"
            with self.assertRaisesRegex(RuntimeError, "storage"):
                self.job().run_owned([sys.executable, "-c", code],
                                     Path(d), time.time() + 10, min_free=0, max_bytes=500)
            self.assertTrue(path.exists())

    def test_success_records_pid_and_output(self):
        with tempfile.TemporaryDirectory() as d:
            result = self.job().run_owned([sys.executable, "-c", "print('ok')"],
                                          Path(d), time.time() + 10, min_free=0, max_bytes=100000)
            self.assertEqual(result["returncode"], 0)
            self.assertGreater(result["pid"], 0)
            self.assertIn("ok", (Path(d) / "job.log").read_text())

    def test_pause_file_blocks_new_job(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "PAUSE").touch()
            with self.assertRaisesRegex(RuntimeError, "paused"):
                self.job().run_owned([sys.executable, "-c", "print('not started')"],
                                     Path(d), time.time() + 10, min_free=0, max_bytes=100000)

    def test_resume_preserves_prior_log_and_adds_new_output(self):
        job=self.job()
        with tempfile.TemporaryDirectory() as d:
            for text in ["first","second"]:
                job.run_owned([sys.executable,"-c",f"print({text!r})"],
                              Path(d),time.time()+10,min_free=0,max_bytes=100000)
            log=(Path(d)/"job.log").read_text()
            self.assertIn("first",log)
            self.assertIn("second",log)

    def test_failed_job_leaves_explicit_failure_record(self):
        job=self.job()
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(RuntimeError):
                job.run_owned([sys.executable,"-c","raise SystemExit(9)"],
                              Path(d),time.time()+10,min_free=0,max_bytes=100000)
            events=list((Path(d)/"job-events").glob("*.json"))
            self.assertEqual(len(events),1,"No durable job result")
            result=json.loads(events[0].read_text())
            self.assertEqual(result["state"],"failed")
            self.assertEqual(result["returncode"],9)
            self.assertIn("exit 9",result["error"])

    def test_polling_throttles_storage_but_forces_final_check(self):
        job=self.job()
        process=Mock(pid=123,returncode=0)
        process.poll.side_effect=[None,None,None,0,0]
        with tempfile.TemporaryDirectory() as d:
            with patch.object(job.subprocess,"Popen",return_value=process), \
                 patch.object(job.time,"monotonic",return_value=0), \
                 patch.object(job.time,"sleep"), \
                 patch.object(job.shutil,"disk_usage",return_value=SimpleNamespace(free=100000)) as usage:
                job.run_owned(["fixture"],Path(d),time.time()+10,min_free=0,max_bytes=100000)
                self.assertEqual(usage.call_count,2,"Only initial and final scans are due")

    def test_successful_child_cannot_skip_final_storage_check(self):
        job=self.job()
        process=Mock(pid=123,returncode=0)
        process.poll.return_value=0
        with tempfile.TemporaryDirectory() as d:
            with patch.object(job.subprocess,"Popen",return_value=process), \
                 patch.object(job.time,"monotonic",return_value=0), \
                 patch.object(job.shutil,"disk_usage",side_effect=[
                     SimpleNamespace(free=100000),SimpleNamespace(free=0)]):
                with self.assertRaisesRegex(RuntimeError,"storage"):
                    job.run_owned(["fixture"],Path(d),time.time()+10,min_free=1,max_bytes=100000)
            record=json.loads(next((Path(d)/"job-events").glob("*.json")).read_text())
            self.assertEqual(record["state"],"failed")
            self.assertEqual(record["returncode"],0)


if __name__ == "__main__":
    unittest.main()
