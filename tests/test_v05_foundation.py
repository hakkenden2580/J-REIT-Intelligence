from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from check_git_boundary import tracked_files, violations
from evidence import metric_evidence
from serve_local import (is_blocked_path, normalized_request_path,
                         sanitized_import_status, sanitized_quality_status)


class EvidenceContractTests(unittest.TestCase):
    def test_fictional_evidence_has_required_fields(self):
        fixture = json.loads((ROOT / "tests/fixtures/fictional-source-evidence.json").read_text())
        schema = json.loads((ROOT / "schema/source-evidence.schema.json").read_text())
        self.assertEqual(set(schema["required"]) - set(fixture), set())
        self.assertEqual(set(schema["properties"]["locator"]["required"]) - set(fixture["locator"]), set())
        self.assertEqual(set(schema["properties"]["extraction"]["required"]) - set(fixture["extraction"]), set())
        self.assertEqual(set(schema["properties"]["review"]["required"]) - set(fixture["review"]), set())

    def test_metric_evidence_is_per_numeric_field(self):
        record = {"as_of_date": "2026-06-30", "cap": 4.2, "noi": 123.4, "occupancy": None}
        source = {"document_id": "doc-0123456789abcdefabcd", "retrieved_at": "2026-07-15T00:00:00+00:00"}
        evidence = metric_evidence(record, source, {"cap": "鑑定!G12", "noi": "収益!H20"}, parser_name="test")
        self.assertEqual(set(evidence), {"cap", "noi"})
        self.assertEqual(evidence["cap"]["locator"]["sheet"], "鑑定")
        self.assertEqual(evidence["cap"]["locator"]["cell"], "G12")
        self.assertEqual(evidence["noi"]["unit"], "million_jpy")

    def test_demo_dataset_is_explicitly_fictional(self):
        demo = json.loads((ROOT / "data/demo-properties.json").read_text())
        self.assertEqual(demo["meta"]["dataset"], "demo")


class GitBoundaryTests(unittest.TestCase):
    def test_no_private_data_is_tracked(self):
        self.assertEqual(violations(tracked_files()), [])

    def test_private_and_git_paths_are_not_served(self):
        for path in (
            "/private-data/raw/source.xlsx",
            "/%70rivate-data/normalized/properties.json",
            "/sources/raw/source.xlsx",
            "/.git/config",
            "/data/properties.json",
        ):
            self.assertTrue(is_blocked_path(normalized_request_path(path)), path)
        self.assertFalse(is_blocked_path(normalized_request_path("/data/demo-properties.json")))

    def test_runtime_import_status_excludes_source_details(self):
        status = sanitized_import_status({
            "run_id": "run-fictional", "status": "succeeded", "finished_at": "2026-07-15T00:00:00+00:00",
            "same_inputs_as_run_id": "run-previous", "layout_statuses": {"fictional": "unchanged"},
            "totals": {"adapters": 1, "properties": 1, "issues": 0},
            "idempotency_key": "secret", "adapters": [{"source_assets": [{"download_url": "secret"}]}],
        })
        self.assertEqual(status["layout_status"], "unchanged")
        self.assertTrue(status["same_inputs"])
        self.assertNotIn("idempotency_key", status)
        self.assertNotIn("adapters", status)

    def test_runtime_quality_status_excludes_property_level_details(self):
        status = sanitized_quality_status({
            "status": "warning", "generated_at": "2026-07-15T00:00:00+00:00",
            "totals": {"properties": 1, "warnings": 1},
            "by_reit": {}, "metrics": {}, "checks": [],
            "issue_samples": {"missing_coordinates": ["SECRET-ID"]},
        })
        self.assertEqual(status["status"], "warning")
        self.assertNotIn("issue_samples", status)
        self.assertNotIn("SECRET-ID", json.dumps(status))


if __name__ == "__main__":
    unittest.main()
