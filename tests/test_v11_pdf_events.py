from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from serve_local import sanitized_pdf_supplement


def fictional_supplement() -> dict:
    evidence = {
        "metric_code": "acquisition_price_million_yen",
        "value": 32100,
        "unit": "million_jpy",
        "observed_at": "2026-06-30",
        "source_document_id": "SECRET-DOCUMENT-ID",
        "retrieved_at": "2026-07-16T00:00:00+00:00",
        "locator": {"type": "pdf_bbox", "page": 11, "bbox": [1, 2, 3, 4]},
        "extraction": {
            "parser": "fictional_pdf", "parser_version": "0.11.0",
            "method": "deterministic_pdf_text", "confidence": 0.9,
        },
        "review": {"status": "pending", "reviewed_by": "SECRET-REVIEWER"},
    }
    return {
        "meta": {
            "dataset": "fictional-pdf-local", "data_engine_version": "0.11.0",
            "publisher": "Fictional REIT", "reit_code": "0000", "period": "Fictional FY2026",
            "as_of_date": "2026-06-30", "notice": "Fictional only",
            "source": {
                "document": "Fictional Presentation", "period": "Fictional FY2026",
                "url": "https://example.invalid/library", "download_url": "https://example.invalid/SECRET.pdf",
                "sha256": "SECRET-SHA256", "document_id": "SECRET-DOCUMENT-ID",
                "retrieved_at": "2026-07-16T00:00:00+00:00",
            },
        },
        "portfolio_metrics": [{
            "metric_code": "occupancy_rate_percent", "value": 98.5, "unit": "percent",
            "period": "Fictional FY2026", "as_of_date": "2026-06-30", "evidence": evidence,
        }],
        "property_events": [{
            "property_name": "Fictional Alpha", "reit": "Fictional REIT", "reit_code": "0000",
            "event_type": "acquisition_planned", "announced_period": "Fictional FY2026",
            "as_of_date": "2026-06-30", "price_million_yen": 32100,
            "noi_yield_percent": 3.3, "evidence": {"price_million_yen": evidence},
        }],
    }


class PdfEventRuntimeTests(unittest.TestCase):
    def test_browser_payload_keeps_display_evidence_and_removes_secrets(self):
        payload = sanitized_pdf_supplement(fictional_supplement())
        rendered = json.dumps(payload)
        self.assertEqual(payload["property_events"][0]["evidence"]["price_million_yen"]["locator"]["page"], 11)
        self.assertEqual(payload["property_events"][0]["evidence"]["price_million_yen"]["locator"]["bbox"], [1, 2, 3, 4])
        self.assertEqual(payload["meta"]["source"]["url"], "https://example.invalid/library")
        for secret in ("SECRET-SHA256", "SECRET-DOCUMENT-ID", "SECRET-REVIEWER", "SECRET.pdf"):
            self.assertNotIn(secret, rendered)

    def test_non_http_source_url_is_not_exposed(self):
        record = fictional_supplement()
        record["meta"]["source"]["url"] = "javascript:alert(1)"
        payload = sanitized_pdf_supplement(record)
        self.assertEqual(payload["meta"]["source"]["url"], "")


if __name__ == "__main__":
    unittest.main()
