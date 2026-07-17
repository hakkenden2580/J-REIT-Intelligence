from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class StableChartTests(unittest.TestCase):
    def test_gap_segments_and_width_guard(self):
        script = r"""
const chart = require("./chart-renderer.js");
const segmented = chart.segmentSeries([3.4, 3.3, null, null, 3.1, 3.0]);
console.log(JSON.stringify({
  solid: segmented.solid.map(segment => segment.map(point => point.index)),
  gaps: segmented.gaps.map(gap => gap.map(point => point.index)),
  points: segmented.points.map(point => point.value),
  normalWidth: chart.stableChartWidth(1180, 1440),
  runawayWidth: chart.stableChartWidth(999999, 1440),
  mobileWidth: chart.stableChartWidth(280, 280),
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
        self.assertEqual(payload["solid"], [[0, 1], [4, 5]])
        self.assertEqual(payload["gaps"], [[1, 4]])
        self.assertEqual(payload["points"], [3.4, 3.3, 3.1, 3.0])
        self.assertEqual(payload["normalWidth"], 1180)
        self.assertEqual(payload["runawayWidth"], 1440)
        self.assertEqual(payload["mobileWidth"], 280)

    def test_hover_uses_overlay_without_redrawing_base_chart(self):
        javascript = (ROOT / "app.js").read_text(encoding="utf-8")
        interaction = javascript.split("function bindComparisonInteraction", 1)[1].split(
            "function drawComparisonChart", 1
        )[0]
        history_interaction = javascript.split("function bindHistoryInteraction", 1)[1].split(
            "function drawHistory", 1
        )[0]

        self.assertIn("drawComparisonHover", interaction)
        self.assertNotIn("drawComparisonChart(", interaction)
        self.assertIn("drawHistoryHover", history_interaction)
        self.assertNotIn("drawHistory(", history_interaction)
        self.assertNotIn("setPointerCapture", javascript)
        self.assertIn("PIPChart.stageSize", javascript)
        self.assertIn("bindStableChartResize", javascript)

    def test_chart_contract_and_missing_value_disclosure(self):
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        javascript = (ROOT / "app.js").read_text(encoding="utf-8")
        css = (ROOT / "comparison-analysis.css").read_text(encoding="utf-8")
        detail_css = (ROOT / "chart-polish.css").read_text(encoding="utf-8")

        self.assertIn("J-REIT Intelligence v0.21", html)
        self.assertIn('src="chart-renderer.js"', html)
        self.assertIn("comparison-chart-overlay", javascript)
        self.assertIn("history-chart-overlay", javascript)
        self.assertIn("点線は前後の開示値を視覚的に結ぶだけ", javascript)
        self.assertIn("値は推定していません", javascript)
        self.assertIn("overflow:hidden", css.replace(" ", ""))
        self.assertIn(".history-chart-overlay", detail_css)
        self.assertIn("pointer-events: none", detail_css)


if __name__ == "__main__":
    unittest.main()
