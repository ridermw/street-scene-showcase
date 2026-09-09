import importlib.util
import unittest
from pathlib import Path


class CaptureTests(unittest.TestCase):
    def capture(self):
        path=Path(__file__).resolve().parents[1]/"pipeline/capture.py"
        self.assertTrue(path.exists(), "Capture gate is not implemented")
        spec=importlib.util.spec_from_file_location("capture",path)
        module=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_wrong_owner_engine_or_device_is_rejected(self):
        gate=self.capture()
        expected={"owner":"run","engine":"CYCLES","device":"GPU","backend":"METAL"}
        gate.validate_capture(expected,dict(expected))
        for key,bad in [("owner","other"),("engine","EEVEE"),("device","CPU"),("backend","NONE")]:
            actual=dict(expected)
            actual[key]=bad
            with self.subTest(key=key):
                with self.assertRaises(ValueError):
                    gate.validate_capture(expected,actual)

    def test_forecast_includes_encoding_retry_and_storage_reserve(self):
        result=self.capture().forecast(120,[10,20],[1000,2000],60,120,.25,5000)
        self.assertEqual(result["seconds"],3180)
        self.assertEqual(result["bytes"],485000)
        self.assertEqual(result["sample_count"],2)

    def test_missing_or_invalid_timings_cannot_approve_delivery(self):
        for timings in [[],[0],[float("nan")],[-1]]:
            with self.subTest(timings=timings):
                with self.assertRaises(ValueError):
                    self.capture().forecast(120,timings,[100],60,120,.25,0)

    def test_delivery_requires_current_reference_and_capture_approval(self):
        gate=self.capture()
        approval={"fingerprint":"current","decision":"accept",
                  "reference_fingerprint":"ref","seconds":100,"bytes":1000}
        gate.delivery_gate(approval,"current","ref",200,2000)
        for key,value in [("fingerprint","old"),("reference_fingerprint","old"),
                          ("decision","improve"),("seconds",300),("bytes",3000),
                          ("bytes",float("nan"))]:
            with self.subTest(key=key):
                bad=dict(approval)
                bad[key]=value
                with self.assertRaises(ValueError):
                    gate.delivery_gate(bad,"current","ref",200,2000)

    def test_delivery_rejects_undefined_remaining_capacity(self):
        gate=self.capture()
        approval={"fingerprint":"current","decision":"accept",
                  "reference_fingerprint":"ref","seconds":100,"bytes":1000}
        for invalid in [float("nan"),float("inf"),float("-inf"),0,-1]:
            for remaining,available in [(invalid,2000),(200,invalid)]:
                with self.subTest(remaining=remaining,available=available):
                    with self.assertRaises(ValueError):
                        gate.delivery_gate(approval,"current","ref",remaining,available)

    def test_locked_scene_retains_its_original_owner(self):
        resolve=getattr(self.capture(),"capture_owner",None)
        self.assertIsNotNone(resolve,"Frozen scene adoption is not implemented")
        config={"run_id":"delivery","scene_owner":"original","locked_scene_sha256":"approved"}
        self.assertEqual(resolve(config,"approved"),"original")
        with self.assertRaises(ValueError):
            resolve(config,"changed")
        for bad in [{"run_id":"delivery","scene_owner":"original"},
                    dict(config,scene_owner=""),dict(config,scene_owner=None)]:
            with self.subTest(config=bad):
                with self.assertRaises(ValueError):
                    resolve(bad,"approved")

    def test_new_scene_uses_current_run_owner(self):
        resolve=getattr(self.capture(),"capture_owner",None)
        self.assertIsNotNone(resolve,"Frozen scene adoption is not implemented")
        self.assertEqual(resolve({"run_id":"current"},"scene-hash"),"current")


if __name__=="__main__":
    unittest.main()
