from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class AverageAlignmentTests(unittest.TestCase):
    def test_cross_reit_dates_align_to_calendar_half_year(self):
        script = r"""
const analysis = require("./analysis-math.js");
const properties = [
  {periods: [
    {as_of_date: "2024-06-30", appraisal: 100},
    {as_of_date: "2024-12-31", appraisal: 110},
  ]},
  {periods: [
    {as_of_date: "2024-03-31", appraisal: 200},
    {as_of_date: "2024-09-30", appraisal: 210},
  ]},
  {periods: [
    {as_of_date: "2024-02-29", appraisal: 300},
    {as_of_date: "2024-08-31", appraisal: 330},
  ]},
];
const timeline = analysis.buildComparisonTimeline(properties);
const series = properties.map(property =>
  analysis.buildComparisonSeries(property, "appraisal", timeline)
);
const aggregate = analysis.coverageAwareAverage(series);
console.log(JSON.stringify({timeline, series, aggregate}));
"""
        result = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=True,
        )
        payload = json.loads(result.stdout)
        self.assertEqual(
            payload["timeline"],
            [
                {"key": "2024-H1", "label": "2024-06"},
                {"key": "2024-H2", "label": "2024-12"},
            ],
        )
        self.assertEqual(payload["series"], [[100, 110], [200, 210], [300, 330]])
        self.assertEqual(payload["aggregate"]["average"], [200, 650 / 3])
        self.assertEqual(payload["aggregate"]["counts"], [3, 3])
        self.assertEqual(payload["aggregate"]["minimumCount"], 1)

    def test_latest_disclosure_wins_within_same_half_year(self):
        script = r"""
const analysis = require("./analysis-math.js");
const property = {periods: [
  {as_of_date: "2025-03-31", cap: 4.2},
  {as_of_date: "2025-06-30", cap: 4.0},
]};
const timeline = analysis.buildComparisonTimeline([property]);
console.log(JSON.stringify({
  timeline,
  series: analysis.buildComparisonSeries(property, "cap", timeline),
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
        self.assertEqual(payload["series"], [4])

    def test_large_selection_hides_low_coverage_average(self):
        script = r"""
const analysis = require("./analysis-math.js");
const series = Array.from({length: 48}, (_, index) => [
  index < 45 ? 30000 + index : null,
  index === 0 ? 22000 : null,
  index < 44 ? 31000 + index : null,
]);
console.log(JSON.stringify(analysis.coverageAwareAverage(series)));
"""
        result = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=True,
        )
        payload = json.loads(result.stdout)
        self.assertEqual(payload["minimumCount"], 5)
        self.assertEqual(payload["counts"], [45, 1, 44])
        self.assertIsNotNone(payload["average"][0])
        self.assertIsNone(payload["average"][1])
        self.assertIsNotNone(payload["average"][2])

    def test_ui_explains_alignment_and_coverage(self):
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        javascript = (ROOT / "app.js").read_text(encoding="utf-8")

        self.assertIn("J-REIT Intelligence v0.21", html)
        self.assertIn("PIPAnalysis.buildComparisonTimeline", javascript)
        self.assertIn("PIPAnalysis.buildComparisonSeries", javascript)
        self.assertIn("PIPAnalysis.distributionSeries", javascript)
        self.assertIn("暦年の上期・下期", javascript)
        self.assertIn("母数10%（最低3件）未満", javascript)
        self.assertIn("coveragePercent", javascript)


if __name__ == "__main__":
    unittest.main()
