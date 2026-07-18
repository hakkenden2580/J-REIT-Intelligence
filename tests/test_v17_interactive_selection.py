from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class InteractiveSpatialSelectionTests(unittest.TestCase):
    def test_destination_point_keeps_requested_radius(self):
        script = r"""
const spatial = require("./spatial-analysis.js");
const center = {lat:35.6812,lng:139.7671};
const destination = spatial.destinationPoint(center,12.5);
console.log(JSON.stringify({
  destination,
  distance: spatial.haversineKm(center,destination),
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
        self.assertIsNotNone(payload["destination"])
        self.assertAlmostEqual(payload["distance"], 12.5, places=6)

    def test_interactive_map_controls_and_fifty_property_limit(self):
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        javascript = (ROOT / "app.js").read_text(encoding="utf-8")
        spatial_css = (ROOT / "spatial-analysis.css").read_text(encoding="utf-8")
        comparison_css = (ROOT / "comparison-analysis.css").read_text(encoding="utf-8")

        self.assertIn("J-REIT Intelligence v0.22", html)
        self.assertIn('id="radiusKm" type="range"', html)
        self.assertIn('max="50"', html)
        for control_id in ("toggleBoxSelection", "clearBoxSelection", "radiusValue"):
            self.assertIn(f'id="{control_id}"', html)
        self.assertIn("comparisonLimit=50", javascript)
        self.assertIn("draggable:true", javascript)
        self.assertIn("PIPSpatialAnalysis.destinationPoint", javascript)
        self.assertIn("L.rectangle", javascript)
        self.assertIn("map.dragging.disable()", javascript)
        self.assertIn("PIPMapAnalysis.boundsContain", javascript)
        self.assertIn(".radius-resize-handle", spatial_css)
        self.assertIn(".box-selecting", spatial_css)
        self.assertIn("overflow:auto", comparison_css)

    def test_selection_remains_a_browser_only_operation(self):
        javascript = (ROOT / "app.js").read_text(encoding="utf-8")
        self.assertNotIn("property.selected=", javascript)
        self.assertNotIn("property.radius=", javascript)
        self.assertNotIn("property.bounds=", javascript)
        self.assertIn("localStorage.setItem(comparisonStorageKey", javascript)


if __name__ == "__main__":
    unittest.main()
