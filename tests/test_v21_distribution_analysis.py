from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DistributionAnalysisTests(unittest.TestCase):
    def test_distribution_series_calculates_median_and_interquartile_range(self):
        script = r"""
const analysis = require("./analysis-math.js");
const series = [
  [1, 10, 100],
  [2, 20, 200],
  [3, 30, null],
  [4, 40, null],
  [100, 50, null],
];
console.log(JSON.stringify(analysis.distributionSeries(series, 3)));
"""
        result = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=True,
        )
        payload = json.loads(result.stdout)
        self.assertEqual(payload["counts"], [5, 5, 2])
        self.assertEqual(payload["average"][:2], [22, 30])
        self.assertEqual(payload["median"][:2], [3, 30])
        self.assertEqual(payload["q1"][:2], [2, 20])
        self.assertEqual(payload["q3"][:2], [4, 40])
        self.assertIsNone(payload["average"][2])
        self.assertIsNone(payload["median"][2])
        self.assertIsNone(payload["q1"][2])
        self.assertIsNone(payload["q3"][2])

    def test_range_band_does_not_bridge_missing_periods(self):
        script = r"""
const chart = require("./chart-renderer.js");
const segments = chart.rangeSegments(
  [2, 3, null, 5, 6],
  [4, 5, null, 7, 8]
);
console.log(JSON.stringify(segments.map(segment => segment.map(point => point.index))));
"""
        result = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=True,
        )
        payload = json.loads(result.stdout)
        self.assertEqual(payload, [[0, 1], [3, 4]])

    def test_distribution_analysis_ui_contract(self):
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        javascript = (ROOT / "app.js").read_text(encoding="utf-8")
        css = (ROOT / "comparison-analysis.css").read_text(encoding="utf-8")
        renderer = (ROOT / "chart-renderer.js").read_text(encoding="utf-8")

        self.assertIn("J-REIT Intelligence v0.22", html)
        self.assertIn("PIPAnalysis.distributionSeries", javascript)
        self.assertIn("latestDistributionSnapshot", javascript)
        self.assertIn("PIPChart.drawRangeBand", javascript)
        self.assertIn("中央値", javascript)
        self.assertIn("中央50%", javascript)
        self.assertIn("開示カバレッジ", javascript)
        self.assertIn(".distribution-summary", css)
        self.assertIn(".comparison-swatch.range", css)
        self.assertIn("function drawRangeBand", renderer)


if __name__ == "__main__":
    unittest.main()
