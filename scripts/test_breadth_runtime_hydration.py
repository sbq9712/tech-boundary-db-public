#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "hydrate_breadth_runtime", ROOT / "scripts" / "hydrate_breadth_runtime.py"
)
assert SPEC and SPEC.loader
HYDRATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(HYDRATE)


def write_manifest_data(path: Path, records: int = 3, shards: int = 2) -> None:
    value = {
        "meta": {
            "records_total": records,
            "total_shards": shards,
            "data_version": "fixture-v1",
        },
        "shards": [{"path": "data/processed/records-2026-01.json", "records": records}],
    }
    path.write_text("window.__MANIFEST__=" + json.dumps(value) + ";\n", encoding="utf-8")


class BreadthRuntimeHydrationTests(unittest.TestCase):
    def make_fixture(self) -> Path:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        processed = Path(temporary.name) / "processed"
        processed.mkdir()
        write_manifest_data(processed / "manifest-data.js")
        (processed / "manifest.json").write_text(
            json.dumps(
                {
                    "meta": {"records_total": 2, "total_shards": 2, "data_version": "older"},
                    "shards": [
                        {"path": "data/processed/records-2026-01.json", "records": 3}
                    ],
                }
            ),
            encoding="utf-8",
        )
        (processed / "records-2026-01.json").write_text("[]", encoding="utf-8")
        (processed / "conferences.json").write_text("[]", encoding="utf-8")
        (processed / "intelligence.json").write_text("[]", encoding="utf-8")
        rows = [
            [
                {"t": "A", "c": "测试/甲", "lv": 3, "sc": 9, "d": "2026-01-03"},
                {"t": "B", "c": "测试/乙", "lv": 1, "sc": 5, "d": "2026-01-02"},
            ],
            [{"t": "C", "c": "测试/甲", "lv": 0, "aip": 1, "d": "2026-01-01"}],
        ]
        for index, part in enumerate(rows):
            (processed / f"lite-part-{index}.js").write_text(
                "window.__LITE_PARTS__.push(" + json.dumps(part) + ");",
                encoding="utf-8",
            )
        for prefix in ("meta-part", "summary-part"):
            for index in range(2):
                (processed / f"{prefix}-{index}.js").write_text(
                    "window.__TEST__.push([]);", encoding="utf-8"
                )
        return processed

    def test_validates_inline_manifest_and_complete_shard_sets(self) -> None:
        processed = self.make_fixture()
        errors = HYDRATE.validate_structure(
            processed,
            expected_records=3,
            expected_shards=2,
            expected_data_version="fixture-v1",
            expected_upstream_files=None,
        )
        self.assertEqual(errors, [])

    def test_missing_middle_shard_fails_closed(self) -> None:
        processed = self.make_fixture()
        (processed / "meta-part-1.js").unlink()
        errors = HYDRATE.validate_structure(
            processed,
            expected_records=3,
            expected_shards=2,
            expected_data_version="fixture-v1",
            expected_upstream_files=None,
        )
        self.assertTrue(any("meta-part shard set mismatch" in error for error in errors))

    def test_builds_boundary_alert_and_category_snapshots(self) -> None:
        processed = self.make_fixture()
        HYDRATE.build_derived(processed.parent)
        alerts = json.loads((processed / "alert-records.json").read_text(encoding="utf-8"))
        categories = json.loads(
            (processed / "category-counts.json").read_text(encoding="utf-8")
        )
        self.assertEqual(alerts["total"], 1)
        self.assertEqual(alerts["items"][0]["title"], "A")
        self.assertEqual(categories["record_total"], 3)
        self.assertEqual(categories["data_version"], "fixture-v1")

    def test_inventory_detects_same_path_content_tampering(self) -> None:
        processed = self.make_fixture()
        inventory = HYDRATE.build_inventory(processed, ["manifest-data.js"])
        original = processed / "manifest-data.js"
        original.write_text("x" * original.stat().st_size, encoding="utf-8")
        errors = HYDRATE.validate_inventory(processed, inventory, "upstream")
        self.assertEqual(errors, ["upstream SHA-256 mismatch: manifest-data.js"])

    def test_startup_hydrates_before_docker_build(self) -> None:
        source = (ROOT / "start_with_local_ai.sh").read_text(encoding="utf-8")
        hydrate_at = source.index('python3 "$ROOT/scripts/hydrate_breadth_runtime.py"')
        docker_at = source.index("docker compose")
        self.assertLess(hydrate_at, docker_at)

    def test_web_build_has_independent_runtime_guard(self) -> None:
        source = (ROOT / "web" / "Dockerfile").read_text(encoding="utf-8")
        for name in (
            "manifest-data.js",
            "manifest.json",
            "alert-records.json",
            "category-counts.json",
        ):
            self.assertIn(name, source)
        self.assertIn('test "$count" -eq 30', source)


if __name__ == "__main__":
    unittest.main()
