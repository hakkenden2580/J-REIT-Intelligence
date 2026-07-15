from __future__ import annotations

import gzip
import json
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from data_engine.change_detection import archive_snapshot, compare_datasets, semantic_fingerprint
from serve_local import sanitized_change_status


def evidence(value: float, document: str = "doc-fictional-a") -> dict:
    return {
        "metric_code": "cap_rate_percent",
        "value": value,
        "unit": "percent",
        "source_document_id": document,
        "retrieved_at": "2026-07-15T00:00:00+00:00",
        "locator": {
            "type": "excel_cell", "page": None, "sheet": "架空物件",
            "cell": "B2", "cell_range": "B2", "bbox": None,
        },
    }


def property_record(identifier: str = "FICTIONAL-001", cap: float = 4.2) -> dict:
    return {
        "id": identifier,
        "reit": "架空投資法人",
        "reit_code": "0000",
        "name": f"架空サンプルビル{identifier[-1]}",
        "type": "オフィス",
        "region": "架空圏",
        "address": f"架空県架空市{identifier[-1]}-1",
        "lat": 35.0,
        "lng": 139.0,
        "periods": [{
            "period_no": 1,
            "period": "架空第1期",
            "as_of_date": "2026-06-30",
            "cap": cap,
            "evidence": {"cap": evidence(cap)},
        }],
    }


def payload(*properties: dict, run_id: str = "run-fictional") -> dict:
    return {
        "meta": {"generated_at": "2026-07-15T00:00:00+00:00", "import_run_id": run_id},
        "properties": list(properties),
    }


class ChangeDetectionTests(unittest.TestCase):
    def test_first_import_creates_zero_delta_baseline(self):
        report = compare_datasets(None, payload(property_record()), import_run_id="run-first")
        self.assertEqual(report["status"], "baseline")
        self.assertEqual(report["totals"]["current_properties"], 1)
        self.assertEqual(report["totals"]["properties_added"], 0)
        self.assertEqual(report["details"]["properties_added"], [])

    def test_semantic_fingerprint_ignores_volatile_evidence_and_meta(self):
        before = payload(property_record())
        after = deepcopy(before)
        after["meta"]["generated_at"] = "2026-07-16T00:00:00+00:00"
        after["properties"][0]["periods"][0]["evidence"]["cap"]["retrieved_at"] = "2026-07-16T00:00:00+00:00"
        self.assertEqual(semantic_fingerprint(before), semantic_fingerprint(after))

    def test_identical_business_values_are_unchanged(self):
        before = payload(property_record(), run_id="run-before")
        after = deepcopy(before)
        after["meta"]["import_run_id"] = "run-after"
        report = compare_datasets(before, after, import_run_id="run-after")
        self.assertEqual(report["status"], "unchanged")
        self.assertEqual(report["totals"]["properties_changed"], 0)
        self.assertEqual(report["totals"]["metric_values_changed"], 0)

    def test_property_and_metric_changes_keep_new_evidence_reference(self):
        before = payload(property_record("FICTIONAL-001", 4.3), property_record("FICTIONAL-REMOVED", 5.0))
        changed = property_record("FICTIONAL-001", 4.2)
        added = property_record("FICTIONAL-ADDED", 3.9)
        after = payload(changed, added, run_id="run-after")
        report = compare_datasets(before, after, import_run_id="run-after")
        self.assertEqual(report["status"], "changed")
        self.assertEqual(report["totals"]["properties_added"], 1)
        self.assertEqual(report["totals"]["properties_removed"], 1)
        self.assertEqual(report["totals"]["properties_changed"], 1)
        self.assertEqual(report["totals"]["metric_values_changed"], 1)
        change = report["details"]["metric_changes"][0]
        self.assertEqual(change["before"], 4.3)
        self.assertEqual(change["after"], 4.2)
        self.assertEqual(change["evidence"]["locator"]["cell"], "B2")

    def test_evidence_relink_is_detected_without_numeric_change(self):
        before = payload(property_record())
        after = deepcopy(before)
        after["properties"][0]["periods"][0]["evidence"]["cap"]["source_document_id"] = "doc-fictional-b"
        report = compare_datasets(before, after)
        self.assertEqual(report["status"], "changed")
        self.assertEqual(report["totals"]["metric_values_changed"], 0)
        self.assertEqual(report["totals"]["evidence_relinked"], 1)

    def test_snapshot_is_compressed_and_deduplicated(self):
        current = payload(property_record())
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            first = archive_snapshot(current, directory)
            second = archive_snapshot(deepcopy(current), directory)
            self.assertEqual(first, second)
            self.assertEqual(len(list(directory.glob("*.json.gz"))), 1)
            with gzip.open(first, "rt", encoding="utf-8") as stream:
                restored = json.load(stream)
            self.assertEqual(restored["properties"][0]["id"], "FICTIONAL-001")

    def test_browser_status_excludes_private_change_details(self):
        before = payload(property_record("FICTIONAL-001", 4.3))
        after = payload(property_record("FICTIONAL-001", 4.2))
        status = sanitized_change_status(compare_datasets(before, after, import_run_id="run-secret"))
        encoded = json.dumps(status, ensure_ascii=False)
        self.assertNotIn("details", status)
        self.assertNotIn("fingerprint", encoded)
        self.assertNotIn("FICTIONAL-001", encoded)
        self.assertNotIn("run-secret", encoded)

    def test_change_fixture_covers_schema_required_fields(self):
        fixture = json.loads((ROOT / "tests/fixtures/fictional-dataset-change-report.json").read_text())
        schema = json.loads((ROOT / "schema/dataset-change-report.schema.json").read_text())
        self.assertEqual(set(schema["required"]) - set(fixture), set())


if __name__ == "__main__":
    unittest.main()
