from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Table, TableStyle

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from data_engine import inspect_pdf_layout, parse_nbf_earnings_presentation
from evidence import pdf_value_evidence


def create_fictional_nbf_pdf(path: Path) -> None:
    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(str(path), pagesize=A4, rightMargin=15 * mm, leftMargin=15 * mm)
    summary = Table([
        ["Metric", "Previous", "Current", "Change", "Rate"],
        ["Rental Income", "43,186", "44,809", "1,623", "3.8%"],
        ["Average Occupancy", "98.9", "98.5", "-0.4pt", "-"],
        ["Portfolio NOI", "30,172", "31,149", "977", "3.2%"],
    ], colWidths=[55 * mm, 27 * mm, 27 * mm, 27 * mm, 27 * mm])
    events = Table([
        ["Property", "Price", "Yield"],
        ["Fictional Alpha", "Acquisition Price 321", "NOI Yield 3.3%"],
        ["Fictional Beta", "Disposal Price 100", "NOI Yield 2.3%"],
    ], colWidths=[55 * mm, 65 * mm, 45 * mm])
    for table in (summary, events):
        table.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dbeafe")),
            ("PADDING", (0, 0), (-1, -1), 6),
        ]))
    doc.build([
        Paragraph("Fictional Earnings Presentation", styles["Title"]),
        PageBreak(),
        Paragraph("1-2 Fictional Profit and Loss", styles["Heading1"]),
        summary,
        PageBreak(),
        Paragraph("2-2 Fictional External Growth", styles["Heading1"]),
        events,
    ])


def fictional_config() -> dict:
    def price(field: str, code: str, labels: list[str]) -> dict:
        return {
            "field": field, "metric_code": code, "unit": "million_jpy",
            "labels": labels, "multiplier": 100,
        }

    yield_metric = {
        "field": "noi_yield_percent", "metric_code": "noi_yield_percent",
        "unit": "percent", "labels": ["NOI Yield"],
    }
    return {
        "publisher": "Fictional REIT", "reit_code": "0000",
        "title": "Fictional Earnings Presentation", "period": "Fictional FY2026",
        "as_of_date": "2026-06-30", "url": "https://example.invalid/library",
        "download_url": "https://example.invalid/fictional.pdf",
        "summary_anchors": ["Profit and Loss", "Rental Income"],
        "growth_anchors": ["2-2", "External Growth"],
        "portfolio_metrics": [
            {"label": "Rental Income", "metric_code": "rental_income_million_yen", "unit": "million_jpy", "value_index": 1},
            {"label": "Average Occupancy", "metric_code": "occupancy_rate_percent", "unit": "percent", "value_index": 1},
            {"label": "Portfolio NOI", "metric_code": "portfolio_noi_million_yen", "unit": "million_jpy", "value_index": 1},
        ],
        "property_events": [
            {"property_name": "Fictional Alpha", "anchor": "Fictional Alpha", "event_type": "acquisition_planned",
             "metrics": [price("price_million_yen", "acquisition_price_million_yen", ["Acquisition Price"]), yield_metric]},
            {"property_name": "Fictional Beta", "anchor": "Fictional Beta", "event_type": "disposal_planned",
             "metrics": [price("price_million_yen", "disposal_price_million_yen", ["Disposal Price"]), yield_metric]},
        ],
    }


class NbfPdfAdapterTests(unittest.TestCase):
    def test_nbf_parser_extracts_summary_and_events_with_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "fictional-nbf.pdf"
            create_fictional_nbf_pdf(path)
            layout = inspect_pdf_layout(path)
            payload, report = parse_nbf_earnings_presentation(path, fictional_config(), layout)
            values = {item["metric_code"]: item["value"] for item in payload["portfolio_metrics"]}
            self.assertEqual(values["rental_income_million_yen"], 44809)
            self.assertEqual(values["occupancy_rate_percent"], 98.5)
            self.assertEqual(values["portfolio_noi_million_yen"], 31149)
            self.assertEqual(len(payload["property_events"]), 2)
            self.assertEqual(payload["property_events"][0]["price_million_yen"], 32100)
            self.assertEqual(payload["property_events"][0]["noi_yield_percent"], 3.3)
            evidence = payload["property_events"][0]["evidence"]["price_million_yen"]
            self.assertEqual(evidence["locator"]["page"], 3)
            self.assertEqual(len(evidence["locator"]["bbox"]), 4)
            self.assertEqual(report["evidence_records"], 7)
            self.assertEqual(report["issues"], [])

    def test_pdf_payload_matches_schema_top_level(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "fictional-nbf.pdf"
            create_fictional_nbf_pdf(path)
            payload, _ = parse_nbf_earnings_presentation(path, fictional_config(), inspect_pdf_layout(path))
            schema = json.loads((ROOT / "schema/nbf-pdf-extraction.schema.json").read_text())
            self.assertEqual(set(schema["required"]) - set(payload), set())

    def test_generic_pdf_evidence_rejects_invalid_confidence(self):
        with self.assertRaises(ValueError):
            pdf_value_evidence(
                metric_code="fictional_metric", unit="count", value=1,
                observed_at="2026-06-30", source={"document_id": "doc-x", "retrieved_at": "2026-07-15T00:00:00Z"},
                page=1, bbox=(1, 2, 3, 4), parser_name="fictional", confidence=1.1,
            )

    def test_official_config_keeps_source_in_private_data(self):
        config = json.loads((ROOT / "config/pdf-sources.json").read_text())["nbf_earnings_49"]
        self.assertTrue(config["local_filename"].endswith(".pdf"))
        self.assertNotIn("/", config["local_filename"])
        self.assertEqual(config["output_filename"], "nbf-49-earnings-presentation.json")
        self.assertEqual(len(config["property_events"]), 5)


if __name__ == "__main__":
    unittest.main()
