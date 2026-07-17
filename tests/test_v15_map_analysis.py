from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class CapMapAnalysisTests(unittest.TestCase):
    def test_cap_bands_bounds_and_bulk_selection(self):
        script = r"""
const mapAnalysis = require("./map-analysis.js");
const bounds = {south:34,north:36,west:138,east:140};
console.log(JSON.stringify({
  bands: [3.4,3.5,4,4.5,5,5.5,null].map(value => mapAnalysis.bandFor(value).key),
  inside: mapAnalysis.boundsContain({lat:35,lng:139},bounds),
  outside: mapAnalysis.boundsContain({lat:37,lng:139},bounds),
  missing: mapAnalysis.boundsContain({lat:null,lng:139},bounds),
  selected: mapAnalysis.selectIds(
    [{id:"B"},{id:"C"},{id:"A"},{id:"D"}],
    new Set(["A"]),
    3
  ),
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
        self.assertEqual(payload["bands"], [
            "under-3-5", "3-5-to-4", "4-to-4-5", "4-5-to-5",
            "5-to-5-5", "over-5-5", "unknown",
        ])
        self.assertTrue(payload["inside"])
        self.assertFalse(payload["outside"])
        self.assertFalse(payload["missing"])
        self.assertEqual(payload["selected"], ["A", "B", "C"])

    def test_map_analysis_ui_contract_is_present(self):
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        javascript = (ROOT / "app.js").read_text(encoding="utf-8")
        css = (ROOT / "map-analysis.css").read_text(encoding="utf-8")
        self.assertIn("J-REIT Intelligence v0.16", html)
        for control_id in (
            "filterMapBounds", "clearMapBounds", "selectVisible",
            "mapActionStatus", "capLegend",
        ):
            self.assertIn(f'id="{control_id}"', html)
        self.assertLess(html.index("map-analysis.js"), html.index("app.js"))
        self.assertIn("PIPMapAnalysis.bandFor", javascript)
        self.assertIn("PIPMapAnalysis.boundsContain", javascript)
        self.assertIn("PIPMapAnalysis.selectIds", javascript)
        self.assertIn('map.on("zoomend"', javascript)
        self.assertIn(".cap-marker", css)
        self.assertIn(".cap-legend", css)

    def test_map_filter_does_not_mutate_or_fabricate_source_data(self):
        javascript = (ROOT / "app.js").read_text(encoding="utf-8")
        self.assertIn("mapBoundsFilter?filtered.filter", javascript)
        self.assertNotIn("property.cap=", javascript)
        self.assertNotIn("property.lat=", javascript)
        self.assertNotIn("property.lng=", javascript)


if __name__ == "__main__":
    unittest.main()
