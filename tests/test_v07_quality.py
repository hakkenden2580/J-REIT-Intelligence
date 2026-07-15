from __future__ import annotations

import json
import sys
import unittest
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from data_engine.quality import evaluate_dataset
from serve_local import sanitized_quality_status


def evidence(value: float) -> dict:
    return {
        "metric_code": "cap_rate_percent",
        "value": value,
        "unit": "percent",
        "observed_at": "2026-06-30",
        "source_document_id": "doc-fictional",
        "retrieved_at": "2026-07-15T00:00:00+00:00",
        "locator": {"type": "excel_cell", "page": None, "sheet": "架空物件", "cell": "A1", "cell_range": "A1", "bbox": None},
        "extraction": {"parser": "fictional", "parser_version": "0.7.0", "method": "test", "confidence": 1.0},
        "review": {"status": "pending", "reviewed_by": None, "reviewed_at": None},
    }


def fictional_property(identifier: str = "FICTIONAL-001") -> dict:
    period = {"period": "架空第1期", "as_of_date": "2026-06-30", "cap": 4.2, "evidence": {"cap": evidence(4.2)}}
    return {
        "id": identifier,
        "reit": "架空投資法人",
        "reit_code": "0000",
        "name": "架空サンプルビル",
        "type": "オフィス",
        "address": "架空県架空市1-1",
        "lat": 35.0,
        "lng": 139.0,
        "cap": 4.2,
        "evidence": {"cap": evidence(4.2)},
        "periods": [period],
    }


class DataQualityTests(unittest.TestCase):
    def test_complete_fictional_dataset_passes(self):
        report = evaluate_dataset({"properties": [fictional_property()]}, import_run_id="run-fictional")
        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["totals"]["properties"], 1)
        self.assertEqual(report["totals"]["periods"], 1)
        self.assertEqual(report["totals"]["numeric_values"], 2)
        self.assertEqual(report["totals"]["evidence_coverage_percent"], 100.0)

    def test_duplicate_id_and_missing_evidence_fail(self):
        first = fictional_property()
        second = deepcopy(first)
        second["evidence"] = {}
        report = evaluate_dataset({"properties": [first, second]})
        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["totals"]["duplicate_ids"], 1)
        self.assertGreater(report["totals"]["errors"], 1)

    def test_out_of_range_occupancy_is_rejected(self):
        item = fictional_property()
        item["occupancy"] = 120
        item["evidence"]["occupancy"] = {**evidence(120), "metric_code": "occupancy_rate_percent"}
        report = evaluate_dataset({"properties": [item]})
        self.assertEqual(report["status"], "failed")
        check = next(value for value in report["checks"] if value["code"] == "numeric_ranges")
        self.assertEqual(check["count"], 1)

    def test_browser_status_excludes_private_issue_samples(self):
        report = evaluate_dataset({"properties": [fictional_property()]}, import_run_id="run-secret")
        report["issue_samples"] = {"missing_coordinates": ["SECRET-PROPERTY-ID"]}
        status = sanitized_quality_status(report)
        self.assertNotIn("issue_samples", status)
        self.assertNotIn("import_run_id", status)
        self.assertNotIn("SECRET-PROPERTY-ID", json.dumps(status))

    def test_quality_fixture_covers_schema_required_fields(self):
        fixture = json.loads((ROOT / "tests/fixtures/fictional-data-quality-report.json").read_text())
        schema = json.loads((ROOT / "schema/data-quality-report.schema.json").read_text())
        self.assertEqual(set(schema["required"]) - set(fixture), set())


if __name__ == "__main__":
    unittest.main()
