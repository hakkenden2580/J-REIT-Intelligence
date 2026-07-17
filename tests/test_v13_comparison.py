from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class MultiPropertyAnalysisTests(unittest.TestCase):
    def test_analysis_math_aligns_dates_and_ignores_missing_values(self):
        script = r"""
const analysis = require("./analysis-math.js");
const properties = [
  {periods: [
    {as_of_date: "2025-06-30", cap: 4.0},
    {as_of_date: "2025-12-31", cap: 3.8},
  ]},
  {periods: [
    {as_of_date: "2025-12-31", cap: 4.2},
    {as_of_date: "2026-06-30", cap: 4.1},
  ]},
];
const timeline = analysis.buildTimeline(properties);
const series = properties.map(item => analysis.buildSeries(item, "cap", timeline));
console.log(JSON.stringify({
  timeline,
  series,
  average: analysis.averageSeries(series),
  summary: analysis.summary(properties[0], "cap"),
}));
"""
        result = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=True,
        )
        payload = json.loads(result.stdout)
        self.assertEqual([item["key"] for item in payload["timeline"]], [
            "2025-06-30", "2025-12-31", "2026-06-30",
        ])
        self.assertEqual(payload["series"], [[4, 3.8, None], [None, 4.2, 4.1]])
        self.assertEqual(payload["average"], [4, 4, 4.1])
        self.assertAlmostEqual(payload["summary"]["change"], -0.2)

    def test_analysis_ui_contract_is_present(self):
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        javascript = (ROOT / "app.js").read_text(encoding="utf-8")
        css = (ROOT / "comparison-analysis.css").read_text(encoding="utf-8")
        self.assertIn("J-REIT Intelligence v0.20", html)
        self.assertIn('id="comparisonButton"', html)
        self.assertIn('id="comparisonDialog"', html)
        self.assertLess(html.index("analysis-math.js"), html.index("app.js"))
        self.assertIn("comparisonLimit=50", javascript)
        for metric in ('"cap"', '"noi"', '"occupancy"', '"appraisal"'):
            self.assertIn(metric, javascript)
        self.assertIn("未開示値の補間は行いません", javascript)
        self.assertIn(".comparison-dialog", css)

    def test_future_unit_metrics_are_not_fabricated_as_active_metrics(self):
        javascript = (ROOT / "app.js").read_text(encoding="utf-8")
        metrics_block = javascript.split("const metrics={", 1)[1].split("};", 1)[0]
        self.assertNotIn("rent_income_per_tsubo", metrics_block)
        self.assertNotIn("unit_price_per_tsubo", metrics_block)
        self.assertIn("貸室賃料収入単価：定義統一後に追加", javascript)


if __name__ == "__main__":
    unittest.main()
