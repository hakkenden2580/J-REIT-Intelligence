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
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from data_engine import (ImportContext, LocalPdfAdapter, extract_page_text,
                         find_labeled_number, inspect_pdf_layout,
                         validate_pdf_layout)
from evidence import pdf_locator, pdf_metric_evidence, source_document
from check_git_boundary import violations


def create_fictional_pdf(path: Path) -> None:
    styles = getSampleStyleSheet()
    document = SimpleDocTemplate(str(path), pagesize=A4, rightMargin=18 * mm, leftMargin=18 * mm)
    table = Table([
        ["Property", "Cap Rate", "NOI"],
        ["Fictional Marunouchi Tower", "3.5", "1,250"],
        ["Fictional Bay Logistics", "4.2", "980"],
    ], colWidths=[90 * mm, 35 * mm, 35 * mm])
    table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dbeafe")),
        ("PADDING", (0, 0), (-1, -1), 6),
    ]))
    story = [
        Paragraph("Fictional REIT Property Report", styles["Title"]),
        Paragraph("Period: Fictional FY2026", styles["BodyText"]),
        table,
        PageBreak(),
        Paragraph("Fictional Marunouchi Tower", styles["Heading1"]),
        Paragraph("Cap Rate 3.5", styles["BodyText"]),
        Paragraph("NOI 1,250", styles["BodyText"]),
    ]
    document.build(story)


class PdfAdapterFoundationTests(unittest.TestCase):
    def test_layout_text_and_table_detection(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "fictional.pdf"
            create_fictional_pdf(path)
            first = inspect_pdf_layout(path)
            second = inspect_pdf_layout(path)
            self.assertEqual(first["page_count"], 2)
            self.assertEqual(first["text_pages"], 2)
            self.assertFalse(first["requires_ocr"])
            self.assertGreaterEqual(first["pages"][0]["table_count"], 1)
            self.assertEqual(first["fingerprint"], second["fingerprint"])
            validation = validate_pdf_layout(first, min_pages=2, required_table_pages=(1,))
            self.assertEqual(validation["status"], "compatible")

    def test_page_text_and_bbox_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "fictional.pdf"
            create_fictional_pdf(path)
            pages = extract_page_text(path, (2,))
            self.assertEqual([item["page"] for item in pages], [2])
            found = find_labeled_number(path, "Cap Rate", page_number=2)
            self.assertIsNotNone(found)
            value, match = found
            self.assertEqual(value, 3.5)
            source = source_document(
                path, publisher="Fictional REIT", title="Fictional Report",
                period="Fictional FY2026", as_of_date="2026-06-30",
                url="https://example.invalid/library", download_url="https://example.invalid/report.pdf",
                media_type="application/pdf",
            )
            evidence = pdf_metric_evidence(
                field="cap", value=value, observed_at="2026-06-30", source=source,
                page=match.page, bbox=match.bbox, parser_name="fictional_pdf", confidence=1.0,
            )
            self.assertEqual(evidence["locator"]["type"], "pdf_bbox")
            self.assertEqual(evidence["locator"]["page"], 2)
            self.assertEqual(len(evidence["locator"]["bbox"]), 4)

    def test_pdf_adapter_rejects_paths_outside_private_raw(self):
        adapter = LocalPdfAdapter(
            source_key="fictional", config={"local_filename": "../secret.pdf"},
            parser=lambda path, config, layout: ({"properties": []}, {"issues": []}),
        )
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            paths = {name: root / name for name in ("raw", "normalized", "cache", "reports", "quarantine")}
            for path in paths.values():
                path.mkdir()
            context = ImportContext(root=root, private_data_dir=root, raw_dir=paths["raw"],
                                    normalized_dir=paths["normalized"], cache_dir=paths["cache"],
                                    reports_dir=paths["reports"], quarantine_dir=paths["quarantine"])
            with self.assertRaises(ValueError):
                adapter.run(context)

    def test_pdf_adapter_returns_pdf_asset_and_layout(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            paths = {name: root / name for name in ("raw", "normalized", "cache", "reports", "quarantine")}
            for path in paths.values():
                path.mkdir()
            create_fictional_pdf(paths["raw"] / "fictional.pdf")
            adapter = LocalPdfAdapter(
                source_key="fictional",
                config={
                    "local_filename": "fictional.pdf", "publisher": "Fictional REIT",
                    "title": "Fictional Report", "period": "Fictional FY2026",
                    "as_of_date": "2026-06-30", "url": "https://example.invalid/library",
                    "download_url": "https://example.invalid/report.pdf", "min_pages": 2,
                    "required_table_pages": [1],
                },
                parser=lambda path, config, layout: (
                    {"meta": {"dataset": "fictional-pdf"}, "properties": [{"id": "FICTIONAL-001"}]},
                    {"issues": []},
                ),
            )
            context = ImportContext(root=root, private_data_dir=root, raw_dir=paths["raw"],
                                    normalized_dir=paths["normalized"], cache_dir=paths["cache"],
                                    reports_dir=paths["reports"], quarantine_dir=paths["quarantine"])
            result = adapter.run(context)
            self.assertEqual(result.source_assets[0].media_type, "application/pdf")
            self.assertEqual(result.layout_reports[0]["validation"]["status"], "compatible")
            self.assertTrue((paths["normalized"] / "fictional-properties.json").is_file())

    def test_pdf_adapter_rejects_output_paths_outside_private_normalized(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            paths = {name: root / name for name in ("raw", "normalized", "cache", "reports", "quarantine")}
            for path in paths.values():
                path.mkdir()
            create_fictional_pdf(paths["raw"] / "fictional.pdf")
            adapter = LocalPdfAdapter(
                source_key="fictional",
                config={
                    "local_filename": "fictional.pdf", "output_filename": "../escaped.json",
                    "publisher": "Fictional REIT", "title": "Fictional Report",
                    "period": "Fictional FY2026", "as_of_date": "2026-06-30",
                    "min_pages": 2, "required_table_pages": [1],
                },
                parser=lambda path, config, layout: ({"properties": []}, {"issues": []}),
            )
            context = ImportContext(root=root, private_data_dir=root, raw_dir=paths["raw"],
                                    normalized_dir=paths["normalized"], cache_dir=paths["cache"],
                                    reports_dir=paths["reports"], quarantine_dir=paths["quarantine"])
            with self.assertRaises(ValueError):
                adapter.run(context)

    def test_blank_pdf_is_flagged_for_ocr(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "scanned-like.pdf"
            pdf = canvas.Canvas(str(path), pagesize=A4)
            pdf.showPage()
            pdf.save()
            layout = inspect_pdf_layout(path)
            self.assertTrue(layout["requires_ocr"])
            self.assertEqual(validate_pdf_layout(layout)["status"], "ocr_required")

    def test_pdf_locator_requires_one_based_page(self):
        with self.assertRaises(ValueError):
            pdf_locator(0, (1, 2, 3, 4))

    def test_pdf_fixture_covers_schema_required_fields(self):
        fixture = json.loads((ROOT / "tests/fixtures/fictional-pdf-layout.json").read_text())
        schema = json.loads((ROOT / "schema/pdf-layout.schema.json").read_text())
        self.assertEqual(set(schema["required"]) - set(fixture), set())

    def test_real_source_documents_are_rejected_by_git_boundary(self):
        self.assertEqual(violations(["documents/actual-report.pdf"]), ["documents/actual-report.pdf"])
        self.assertEqual(violations(["tests/fixtures/fictional-report.pdf"]), [])


if __name__ == "__main__":
    unittest.main()
