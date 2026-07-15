from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from data_engine import AdapterRegistry, AdapterResult, ImportContext, SourceAdapter, SourceAsset, execute_import_run
from data_engine.layout import inspect_workbook_layout, validate_workbook_layout


class FictionalAdapter(SourceAdapter):
    source_key = "fictional"
    adapter_id = "fictional_excel"
    adapter_version = "0.6.0"

    def run(self, context: ImportContext) -> AdapterResult:
        layout = {
            "local_filename": "fictional.xlsx",
            "sheet_count": 1,
            "sheets": [{"name": "架空物件一覧", "max_row": 2, "max_column": 2, "non_empty_cells": 4}],
            "fingerprint": "1" * 64,
            "validation": {"status": "compatible"},
        }
        asset = SourceAsset(
            source_key="fictional", local_filename="fictional.xlsx", sha256="2" * 64,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            publisher="架空投資法人", title="架空物件データ", period="架空第1期",
            as_of_date="2026-06-30", url="https://example.invalid/library",
            download_url="https://example.invalid/fictional.xlsx", layout_fingerprint="1" * 64,
        )
        return AdapterResult(
            source_key=self.source_key, adapter_id=self.adapter_id, adapter_version=self.adapter_version,
            payload={"meta": {"dataset": "fictional"}, "properties": [{"id": "FICTIONAL-001"}]},
            report={"issues": []}, source_assets=[asset], layout_reports=[layout], issues=[],
        )


class FailingAdapter(SourceAdapter):
    source_key = "failing"
    adapter_id = "failing_excel"
    adapter_version = "0.6.0"

    def run(self, context: ImportContext) -> AdapterResult:
        raise ValueError("架空レイアウト不一致")


class DataEngineContractTests(unittest.TestCase):
    def test_layout_fingerprint_is_order_independent(self):
        left = {"架空収益": {"B2": 1}, "架空物件一覧": {"A1": "名称", "D3": 4}}
        right = {"架空物件一覧": {"D3": 4, "A1": "名称"}, "架空収益": {"B2": 1}}
        self.assertEqual(inspect_workbook_layout(left), inspect_workbook_layout(right))

    def test_layout_change_and_missing_sheet_are_detected(self):
        first = inspect_workbook_layout({"架空物件一覧": {"A1": "名称"}})
        changed = inspect_workbook_layout({"架空物件一覧": {"A1": "名称", "C9": 1}})
        self.assertNotEqual(first["fingerprint"], changed["fingerprint"])
        validation = validate_workbook_layout(first, required_sheets=("架空物件一覧", "架空収益"))
        self.assertEqual(validation["status"], "incompatible")
        self.assertEqual(validation["missing_sheets"], ["架空収益"])

    def test_registry_rejects_duplicate_source_keys(self):
        registry = AdapterRegistry()
        registry.register(FictionalAdapter())
        with self.assertRaises(ValueError):
            registry.register(FictionalAdapter())

    def test_import_run_has_stable_idempotency_key(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            paths = {name: root / name for name in ("raw", "normalized", "cache", "reports", "quarantine")}
            for path in paths.values():
                path.mkdir()
            context = ImportContext(root=root, private_data_dir=root, raw_dir=paths["raw"],
                                    normalized_dir=paths["normalized"], cache_dir=paths["cache"],
                                    reports_dir=paths["reports"], quarantine_dir=paths["quarantine"])
            _, first = execute_import_run([FictionalAdapter()], context)
            _, second = execute_import_run([FictionalAdapter()], context)
            self.assertEqual(first["idempotency_key"], second["idempotency_key"])
            self.assertEqual(second["same_inputs_as_run_id"], first["run_id"])
            self.assertEqual(second["layout_statuses"]["fictional_excel:fictional.xlsx"], "unchanged")

    def test_failed_import_run_is_quarantined(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            paths = {name: root / name for name in ("raw", "normalized", "cache", "reports", "quarantine")}
            for path in paths.values():
                path.mkdir()
            context = ImportContext(root=root, private_data_dir=root, raw_dir=paths["raw"],
                                    normalized_dir=paths["normalized"], cache_dir=paths["cache"],
                                    reports_dir=paths["reports"], quarantine_dir=paths["quarantine"])
            with self.assertRaises(ValueError):
                execute_import_run([FailingAdapter()], context)
            records = list(paths["quarantine"].glob("run-*.json"))
            self.assertEqual(len(records), 1)
            record = json.loads(records[0].read_text())
            self.assertEqual(record["status"], "failed")
            self.assertEqual(record["error"]["type"], "ValueError")

    def test_v06_fixtures_cover_schema_required_fields(self):
        for stem in ("workbook-layout", "import-run"):
            fixture = json.loads((ROOT / f"tests/fixtures/fictional-{stem}.json").read_text())
            schema = json.loads((ROOT / f"schema/{stem}.schema.json").read_text())
            self.assertEqual(set(schema["required"]) - set(fixture), set())


if __name__ == "__main__":
    unittest.main()
