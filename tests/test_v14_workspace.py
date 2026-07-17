from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class AnalysisWorkspaceTests(unittest.TestCase):
    def test_filter_sort_and_csv_helpers(self):
        script = r"""
const workspace = require("./workspace-utils.js");
const properties = [
  {id:"A",name:"Alpha",reit:"R1",type:"Office",region:"Tokyo",cap:3.5,occupancy:99,price:100,leasable_area:500},
  {id:"B",name:"Beta",reit:"R2",type:"Office",region:"Osaka",cap:null,occupancy:95,price:300,leasable_area:700},
  {id:"C",name:"Gamma",reit:"R1",type:"Logistics",region:"Tokyo",cap:4.2,occupancy:100,price:200,leasable_area:900},
];
const filtered = workspace.filterAndSort(properties,{reit:"R1",capMin:"3.6",sort:"price-desc"});
const missingExcluded = workspace.filterProperties(properties,{capMin:"3.0"});
console.log(JSON.stringify({
  ids: filtered.map(item=>item.id),
  missingExcluded: missingExcluded.map(item=>item.id),
  csv: workspace.toCsv([{id:"A",name:'A "quoted" name'}],["id","name"]),
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
        self.assertEqual(payload["ids"], ["C"])
        self.assertEqual(payload["missingExcluded"], ["A", "C"])
        self.assertIn('"A ""quoted"" name"', payload["csv"])

    def test_workspace_ui_contract_is_present(self):
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        javascript = (ROOT / "app.js").read_text(encoding="utf-8")
        css = (ROOT / "workspace.css").read_text(encoding="utf-8")
        self.assertIn("J-REIT Intelligence v0.20", html)
        for view in ("map", "table", "analysis"):
            self.assertIn(f'data-view="{view}"', html)
        for filter_id in (
            "capMin", "capMax", "occupancyMin", "occupancyMax",
            "priceMin", "priceMax", "areaMin", "areaMax",
        ):
            self.assertIn(f'id="{filter_id}"', html)
        self.assertIn('id="selectionPanel"', html)
        self.assertIn('id="exportSelected"', html)
        self.assertLess(html.index("workspace-utils.js"), html.index("app.js"))
        self.assertIn("PIPWorkspace.filterAndSort", javascript)
        self.assertIn("pip-comparison-ids-v0.14", javascript)
        self.assertIn("jreit-selected-properties.csv", javascript)
        self.assertIn(".property-table", css)
        self.assertIn(".analysis-view", css)

    def test_unavailable_schema_fields_are_not_fabricated_as_filters(self):
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        self.assertNotIn('id="buildYearMin"', html)
        self.assertNotIn('id="acquisitionDateMin"', html)
        self.assertIn("共通Schemaへ追加後", html)


if __name__ == "__main__":
    unittest.main()
