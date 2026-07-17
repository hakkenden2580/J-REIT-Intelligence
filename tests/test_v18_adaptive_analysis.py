from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class AdaptiveAnalysisTests(unittest.TestCase):
    def test_series_mode_and_pointer_math(self):
        script = r"""
const analysis = require("./analysis-math.js");
console.log(JSON.stringify({
  small: analysis.resolveSeriesMode("auto", 8, 8),
  large: analysis.resolveSeriesMode("auto", 9, 8),
  forcedAverage: analysis.resolveSeriesMode("average", 2, 8),
  forcedIndividual: analysis.resolveSeriesMode("individual", 50, 8),
  first: analysis.nearestTimelineIndex(10, 10, 100, 6),
  middle: analysis.nearestTimelineIndex(60, 10, 100, 6),
  last: analysis.nearestTimelineIndex(120, 10, 100, 6),
  counts: analysis.sampleCounts([[1, null, 3], [2, 2, null], [null, 4, 5]]),
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
        self.assertEqual(payload["small"], "individual")
        self.assertEqual(payload["large"], "average")
        self.assertEqual(payload["forcedAverage"], "average")
        self.assertEqual(payload["forcedIndividual"], "individual")
        self.assertEqual(payload["first"], 0)
        self.assertEqual(payload["middle"], 3)
        self.assertEqual(payload["last"], 5)
        self.assertEqual(payload["counts"], [2, 2, 2])

    def test_adaptive_chart_and_scrubbing_contract(self):
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        javascript = (ROOT / "app.js").read_text(encoding="utf-8")
        css = (ROOT / "comparison-analysis.css").read_text(encoding="utf-8")

        self.assertIn("J-REIT Intelligence v0.20", html)
        self.assertIn("individualSeriesLimit=8", javascript)
        self.assertIn('comparisonSeriesMode="auto"', javascript)
        self.assertIn('data-series-mode="${mode}"', javascript)
        self.assertIn("PIPAnalysis.resolveSeriesMode", javascript)
        self.assertIn("PIPAnalysis.nearestTimelineIndex", javascript)
        self.assertIn('addEventListener("pointermove"', javascript)
        self.assertIn("comparison-chart-tooltip", javascript)
        self.assertIn("グラフ操作で公開値が変更されることはありません", javascript)
        self.assertIn(".series-mode-control", css)
        self.assertIn(".comparison-chart-tooltip", css)

    def test_detailed_property_panel_uses_only_available_fields(self):
        javascript = (ROOT / "app.js").read_text(encoding="utf-8")
        for label in (
            "PROPERTY DETAIL",
            "最新開示",
            "最新指標",
            "物件概要",
            "投資法人",
            "証券コード",
            "賃貸可能面積",
            "賃貸面積",
            "割引率",
            "最終還元利回り",
            "座標",
            "Evidence",
        ):
            self.assertIn(label, javascript)

        # 未収集項目を推測値として物件詳細へ出さない。
        detail_block = javascript.split("function selectProperty(p)", 1)[1].split(
            "function comparedProperties()", 1
        )[0]
        self.assertNotIn("最寄駅", detail_block)
        self.assertNotIn("取得日", detail_block)
        self.assertNotIn("竣工年", detail_block)
        self.assertNotIn("持分形態", detail_block)


if __name__ == "__main__":
    unittest.main()
