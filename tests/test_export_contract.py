import datetime
import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
UTC = datetime.timezone.utc


class ExportContractTests(unittest.TestCase):
    def setUp(self):
        path = ROOT / "tools" / "export_contract.py"
        self.assertTrue(path.is_file(), "Source/export contract is not implemented")
        spec = importlib.util.spec_from_file_location("export_contract", path)
        self.contract = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.contract)
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.readonly = self.root / "source-data"
        self.readonly.mkdir()
        self.source = self.readonly / "scene.blend"
        self.source.write_bytes(b"frozen source fixture")
        self.sha256 = hashlib.sha256(b"frozen source fixture").hexdigest()
        self.staging = self.root / "task-staging"
        self.staging.mkdir()
        self.output = self.staging / "export"

    def verify_output(self, output, **overrides):
        arguments = {
            "staging_root": self.staging,
            "readonly_roots": [self.readonly],
        }
        arguments.update(overrides)
        return self.contract.verify_output_path(self.source, output, **arguments)

    def allowance(self):
        return {
            "enabled": True,
            "started_utc": "2026-01-01T12:00:00Z",
            "deadline_utc": "2026-01-01T12:30:00Z",
            "max_additional_bytes": 1024 ** 3,
            "min_free_bytes": 2 * 1024 ** 3,
            "max_heavy_jobs": 1,
        }

    def validate_allowance(self, config):
        self.contract.validate_allowance(
            config, now=datetime.datetime(2026, 1, 1, 12, 5, tzinfo=UTC))

    def test_exact_source_hash_is_verified_without_writes(self):
        self.assertIsNone(self.contract.verify_source(self.source, self.sha256))
        self.assertEqual(self.source.read_bytes(), b"frozen source fixture")
        self.assertEqual(list(self.readonly.iterdir()), [self.source])

    def test_missing_source_is_rejected(self):
        with self.assertRaises(FileNotFoundError):
            self.contract.verify_source(self.readonly / "missing.blend", self.sha256)

    def test_nonfile_source_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "regular file"):
            self.contract.verify_source(self.readonly, self.sha256)

    def test_changed_source_is_rejected(self):
        self.source.write_bytes(b"different source")
        with self.assertRaisesRegex(ValueError, "SHA256"):
            self.contract.verify_source(self.source, self.sha256)

    def test_missing_or_malformed_expected_hash_is_rejected(self):
        for value in (None, "", "abc", "g" * 64, self.sha256.upper(), 42):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "SHA256"):
                self.contract.verify_source(self.source, value)

    def test_source_timing_uses_zero_origin_without_stretching(self):
        self.assertEqual(self.contract.sample_seconds(1), 0)
        self.assertEqual(self.contract.sample_seconds(61), 2.5)
        self.assertAlmostEqual(self.contract.sample_seconds(120), 119 / 24)
        values = [self.contract.sample_seconds(frame) for frame in range(1, 121)]
        self.assertEqual(len(values), 120)
        for left, right in zip(values, values[1:]):
            self.assertAlmostEqual(right - left, 1 / 24)

    def test_invalid_frames_and_boolean_integers_are_rejected(self):
        for frame in (0, 121, -1, True, False, 1.0, "61", None, float("nan")):
            with self.subTest(frame=frame), self.assertRaises(ValueError):
                self.contract.sample_seconds(frame)

    def test_new_output_is_resolved_without_creating_it(self):
        self.assertEqual(self.verify_output(self.output), self.output)
        self.assertFalse(self.output.exists())

    def test_existing_empty_output_is_allowed(self):
        self.output.mkdir()
        self.assertEqual(self.verify_output(self.output), self.output)

    def test_source_and_hardlink_output_aliases_are_rejected(self):
        alias = self.staging / "source-alias"
        alias.hardlink_to(self.source)
        for output in (self.source, alias):
            with self.subTest(output=output), self.assertRaises(ValueError):
                self.verify_output(output)

    def test_symlink_to_source_or_readonly_directory_is_rejected(self):
        for name, target in (("file-alias", self.source), ("root-alias", self.readonly)):
            alias = self.staging / name
            alias.symlink_to(target)
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.verify_output(alias)
        with self.assertRaises(ValueError):
            self.verify_output(self.staging / "root-alias" / "new-output")

    def test_readonly_roots_and_their_ancestors_are_rejected(self):
        for output in (self.readonly, self.readonly / "new", self.root):
            with self.subTest(output=output), self.assertRaises(ValueError):
                self.verify_output(output)

    def test_staging_must_be_disjoint_from_readonly_roots_and_source(self):
        for staging in (self.readonly, self.root, self.readonly / "new"):
            with self.subTest(staging=staging), self.assertRaises(ValueError):
                self.verify_output(staging / "output", staging_root=staging)
        with self.assertRaises(ValueError):
            self.verify_output(self.root / "export", staging_root=self.root,
                               readonly_roots=[self.root / "other-source"])

    def test_output_must_be_a_strict_staging_descendant(self):
        for output in (self.staging, self.root / "outside", Path("relative-export")):
            with self.subTest(output=output), self.assertRaises(ValueError):
                self.verify_output(output)

    def test_parent_traversal_is_rejected_even_when_it_returns_to_staging(self):
        for output in (self.staging / ".." / "outside",
                       self.staging / "nested" / ".." / "export"):
            with self.subTest(output=output), self.assertRaises(ValueError):
                self.verify_output(output)

    def test_missing_readonly_boundaries_are_rejected(self):
        for roots in ([], None, ["relative-source"]):
            with self.subTest(roots=roots), self.assertRaises(ValueError):
                self.verify_output(self.output, readonly_roots=roots)

    def test_existing_nonempty_export_is_rejected_before_overwrite(self):
        self.output.mkdir()
        retained = self.output / "previous.glb"
        retained.write_bytes(b"retain")
        with self.assertRaisesRegex(ValueError, "empty"):
            self.verify_output(self.output)
        self.assertEqual(retained.read_bytes(), b"retain")

    def test_future_expired_and_reserve_only_allowances_are_rejected(self):
        for start, deadline in (
            ("2026-01-01T12:06:00Z", "2026-01-01T12:30:00Z"),
            ("2026-01-01T11:00:00Z", "2026-01-01T12:04:00Z"),
            ("2026-01-01T12:00:00Z", "2026-01-01T12:10:00Z"),
            ("2026-01-01T12:00:00Z", "2026-01-01T11:00:00Z"),
        ):
            config = self.allowance() | {"started_utc": start, "deadline_utc": deadline}
            with self.subTest(start=start, deadline=deadline), self.assertRaises(ValueError):
                self.validate_allowance(config)

    def test_fresh_bounded_allowance_is_accepted(self):
        self.assertIsNone(self.validate_allowance(self.allowance()))

    def test_resource_values_must_be_positive_finite_integer_bytes(self):
        for field in ("max_additional_bytes", "min_free_bytes"):
            for value in (0, -1, True, 1.5, float("nan"), float("inf"),
                          float("-inf"), "1024", None):
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    self.validate_allowance(self.allowance() | {field: value})

    def test_only_one_heavy_job_and_explicit_activation_are_accepted(self):
        for field, values in (("enabled", (False, 1, "true", None)),
                              ("max_heavy_jobs", (0, 2, True, 1.0, None))):
            for value in values:
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    self.validate_allowance(self.allowance() | {field: value})

    def test_malformed_and_timezone_free_dates_are_rejected(self):
        for field in ("started_utc", "deadline_utc"):
            for value in ("2026-01-01T12:00:00", "not-a-date", None, 123):
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    self.validate_allowance(self.allowance() | {field: value})

    def test_missing_required_resource_fields_are_rejected(self):
        for field in self.allowance():
            config = self.allowance()
            del config[field]
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.validate_allowance(config)

    def test_example_cannot_authorize_an_export(self):
        config = json.loads((ROOT / "configs" / "gltf-export.example.json").read_text())
        with self.assertRaisesRegex(ValueError, "inactive"):
            self.validate_allowance(config)


if __name__ == "__main__":
    unittest.main()
