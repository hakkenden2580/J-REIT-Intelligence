from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from data_engine.quality import evaluate_dataset


def evidence(metric_code: str, value: float, cell: str) -> dict:
    return {
        "metric_code": metric_code,
        "value": value,
        "unit": "percent",
        "observed_at": "2026-06-30",
        "source_document_id": "doc-fictional-terminal-cap",
        "retrieved_at": "2026-07-18T00:00:00+00:00",
        "locator": {
            "type": "excel_cell",
            "page": None,
            "sheet": "架空鑑定一覧",
            "cell": cell,
            "cell_range": cell,
            "bbox": None,
        },
        "extraction": {
            "parser": "fictional_terminal_cap",
            "parser_version": "0.22.0",
            "method": "fixture",
            "confidence": 1.0,
        },
        "review": {
            "status": "pending",
            "reviewed_by": None,
            "reviewed_at": None,
        },
    }


class TerminalCapRateTests(unittest.TestCase):
    def test_terminal_cap_is_a_distinct_evidence_metric(self):
        cap = evidence("cap_rate_percent", 3.4, "K10")
        terminal = evidence("terminal_cap_rate_percent", 3.5, "M10")
        property_record = {
            "id": "FICTIONAL-TCR-001",
            "reit": "架空投資法人",
            "reit_code": "0000",
            "name": "架空ターミナルビル",
            "type": "オフィス",
            "address": "架空県架空市1-1",
            "lat": 35.0,
            "lng": 139.0,
            "cap": 3.4,
            "terminal_cap_rate": 3.5,
            "evidence": {"cap": cap, "terminal_cap_rate": terminal},
            "periods": [
                {
                    "period": "架空第1期",
                    "as_of_date": "2026-06-30",
                    "cap": 3.4,
                    "terminal_cap_rate": 3.5,
                    "evidence": {"cap": cap, "terminal_cap_rate": terminal},
                }
            ],
        }
        report = evaluate_dataset({"properties": [property_record]})
        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["metrics"]["cap"]["available"], 2)
        self.assertEqual(report["metrics"]["terminal_cap_rate"]["available"], 2)
        self.assertEqual(report["metrics"]["terminal_cap_rate"]["coverage_percent"], 100.0)
        self.assertNotEqual(cap["metric_code"], terminal["metric_code"])
        self.assertNotEqual(cap["locator"]["cell"], terminal["locator"]["cell"])

    def test_terminal_cap_filter_and_sort_are_supported(self):
        script = r"""
const workspace = require("./workspace-utils.js");
const properties = [
  {id:"A",name:"Alpha",terminal_cap_rate:3.5},
  {id:"B",name:"Beta",terminal_cap_rate:null},
  {id:"C",name:"Gamma",terminal_cap_rate:4.2},
];
const result = workspace.filterAndSort(
  properties,
  {terminalCapMin:"3.6",terminalCapMax:"4.5",sort:"terminal_cap_rate-desc"}
);
console.log(JSON.stringify(result.map(item => item.id)));
"""
        result = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=True,
        )
        self.assertEqual(json.loads(result.stdout), ["C"])

    def test_terminal_cap_rejects_cap_rate_evidence(self):
        wrong = evidence("cap_rate_percent", 3.5, "M10")
        property_record = {
            "id": "FICTIONAL-TCR-002",
            "reit": "架空投資法人",
            "reit_code": "0000",
            "name": "架空Evidence不整合ビル",
            "type": "オフィス",
            "address": "架空県架空市2-2",
            "lat": 35.0,
            "lng": 139.0,
            "terminal_cap_rate": 3.5,
            "evidence": {"terminal_cap_rate": wrong},
            "periods": [],
        }
        report = evaluate_dataset({"properties": [property_record]})
        self.assertEqual(report["status"], "failed")
        consistency = next(
            item for item in report["checks"]
            if item["code"] == "evidence_consistency"
        )
        self.assertEqual(consistency["count"], 1)
        mismatch = report["issue_samples"]["evidence_mismatches"][0]
        self.assertEqual(mismatch["field"], "terminal_cap_rate")
        self.assertEqual(
            mismatch["expected_metric_code"], "terminal_cap_rate_percent"
        )

    def test_v22_ui_exposes_terminal_cap_and_exact_evidence(self):
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        javascript = (ROOT / "app.js").read_text(encoding="utf-8")
        css = (ROOT / "chart-polish.css").read_text(encoding="utf-8")
        dictionary = json.loads(
            (ROOT / "schema/metric-dictionary.json").read_text(encoding="utf-8")
        )

        self.assertIn("J-REIT Intelligence v0.22", html)
        self.assertIn('id="terminalCapMin"', html)
        self.assertIn('id="terminalCapMax"', html)
        self.assertIn('id="mapYieldMetric"', html)
        self.assertIn("最終還元利回り（TCR）", javascript)
        self.assertIn('data-evidence-metric="terminal_cap_rate"', javascript)
        self.assertIn("TCR − CR スプレッド", javascript)
        self.assertIn("Evidence: ${esc(evidencePosition(evidence))}", javascript)
        self.assertIn("scaledDifference(base.terminal_cap_rate", javascript)
        self.assertIn(".metric-evidence-card", css)
        metric = dictionary["metrics"]["terminal_cap_rate_percent"]
        self.assertEqual(metric["short_label"], "TCR")
        self.assertIn("復帰価格", metric["definition_ja"])


if __name__ == "__main__":
    unittest.main()
