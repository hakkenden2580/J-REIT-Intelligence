from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class SpatialSearchTests(unittest.TestCase):
    def test_haversine_radius_and_validation(self):
        script = r"""
const spatial = require("./spatial-analysis.js");
const center = {lat:35,lng:139,radiusKm:5};
console.log(JSON.stringify({
  zero: spatial.haversineKm(center,{lat:35,lng:139}),
  oneDegree: spatial.haversineKm({lat:35,lng:139},{lat:36,lng:139}),
  inside: spatial.withinRadius({lat:35.02,lng:139},center),
  outside: spatial.withinRadius({lat:35.1,lng:139},center),
  missing: spatial.withinRadius({lat:null,lng:139},center),
  radius: [
    spatial.normalizeRadiusKm("10"),
    spatial.normalizeRadiusKm("100"),
    spatial.normalizeRadiusKm("0"),
    spatial.normalizeRadiusKm("-1"),
    spatial.normalizeRadiusKm("invalid",5),
  ],
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
        self.assertEqual(payload["zero"], 0)
        self.assertGreater(payload["oneDegree"], 110)
        self.assertLess(payload["oneDegree"], 112)
        self.assertTrue(payload["inside"])
        self.assertFalse(payload["outside"])
        self.assertFalse(payload["missing"])
        self.assertEqual(payload["radius"], [10, 50, 0.5, 3, 5])

    def test_radius_search_ui_contract_is_present(self):
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        javascript = (ROOT / "app.js").read_text(encoding="utf-8")
        css = (ROOT / "spatial-analysis.css").read_text(encoding="utf-8")
        self.assertIn("J-REIT Intelligence v0.20", html)
        for control_id in (
            "toggleRadiusSearch", "radiusPanel", "radiusKm",
            "radiusFromCenter", "radiusPick", "clearRadius", "radiusStatus",
        ):
            self.assertIn(f'id="{control_id}"', html)
        self.assertLess(html.index("spatial-analysis.js"), html.index("app.js"))
        self.assertIn("PIPSpatialAnalysis.withinRadius", javascript)
        self.assertIn("PIPSpatialAnalysis.normalizeRadiusKm", javascript)
        self.assertIn('map.on("click"', javascript)
        self.assertIn('id="detailRadiusSearch"', javascript)
        self.assertIn(".radius-panel", css)
        self.assertIn(".radius-circle", css)

    def test_spatial_filter_is_read_only_and_excludes_missing_coordinates(self):
        javascript = (ROOT / "app.js").read_text(encoding="utf-8")
        helper = (ROOT / "spatial-analysis.js").read_text(encoding="utf-8")
        self.assertIn("radiusFilter?bounded.filter", javascript)
        self.assertIn("if(!first||!second)return null", helper)
        self.assertNotIn("property.lat=", javascript)
        self.assertNotIn("property.lng=", javascript)


if __name__ == "__main__":
    unittest.main()
