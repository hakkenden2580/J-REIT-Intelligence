from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from data_engine.pdf_reviews import (
    apply_review_ledger,
    evidence_id,
    iter_supplement_evidence,
    load_review_ledger,
    resolve_evidence_prefix,
    review_summary,
    save_review_ledger,
    upsert_review,
)
from data_engine.pdf_supplements import discover_supplement_paths, load_pdf_supplements
from serve_local import sanitized_pdf_catalog


def fictional_evidence(metric_code: str, value: float, page: int) -> dict:
    return {
        "metric_code": metric_code,
        "value": value,
        "unit": "percent",
        "observed_at": "2026-06-30",
        "source_document_id": "doc-0123456789abcdefabcd",
        "retrieved_at": "2026-07-16T00:00:00+00:00",
        "locator": {
            "type": "pdf_bbox", "page": page, "sheet": None, "cell": None,
            "cell_range": None, "bbox": [1, 2, 3, 4],
        },
        "extraction": {
            "parser": "fictional_pdf", "parser_version": "0.12.0",
            "method": "deterministic_pdf_text", "confidence": 0.9,
        },
        "review": {"status": "pending", "reviewed_by": None, "reviewed_at": None},
    }


def fictional_supplement() -> dict:
    occupancy = fictional_evidence("occupancy_rate_percent", 98.5, 2)
    price = fictional_evidence("acquisition_price_million_yen", 32100, 3)
    price["unit"] = "million_jpy"
    return {
        "meta": {
            "dataset": "fictional-pdf-local", "data_engine_version": "0.12.0",
            "publisher": "Fictional REIT", "reit_code": "0000",
            "period": "Fictional FY2026", "as_of_date": "2026-06-30",
            "source": {
                "document": "Fictional Presentation", "url": "https://example.invalid/library",
                "download_url": "https://example.invalid/SECRET.pdf", "sha256": "SECRET-SHA",
                "document_id": "doc-0123456789abcdefabcd",
                "retrieved_at": "2026-07-16T00:00:00+00:00",
            },
        },
        "portfolio_metrics": [{
            "metric_code": "occupancy_rate_percent", "value": 98.5, "unit": "percent",
            "period": "Fictional FY2026", "as_of_date": "2026-06-30", "evidence": occupancy,
        }],
        "property_events": [{
            "property_name": "Fictional Alpha", "reit": "Fictional REIT", "reit_code": "0000",
            "event_type": "acquisition_planned", "announced_period": "Fictional FY2026",
            "as_of_date": "2026-06-30", "price_million_yen": 32100,
            "noi_yield_percent": None, "evidence": {"price_million_yen": price},
        }],
    }


class PdfEvidenceReviewTests(unittest.TestCase):
    def test_evidence_id_is_stable_and_locator_sensitive(self):
        evidence = fictional_evidence("occupancy_rate_percent", 98.5, 2)
        self.assertEqual(evidence_id(evidence), evidence_id(json.loads(json.dumps(evidence))))
        changed = json.loads(json.dumps(evidence))
        changed["locator"]["page"] = 3
        self.assertNotEqual(evidence_id(evidence), evidence_id(changed))

    def test_review_ledger_is_applied_without_mutating_source(self):
        record = fictional_supplement()
        candidate = next(iter(iter_supplement_evidence(record)))
        ledger = upsert_review(
            {"schema_version": "1.0", "updated_at": None, "reviews": []},
            evidence_identifier=candidate["evidence_id"], status="approved",
            reviewed_by="Fictional Reviewer", note="Fictional check only",
        )
        reviewed = apply_review_ledger(record, ledger)
        self.assertEqual(record["portfolio_metrics"][0]["evidence"]["review"]["status"], "pending")
        self.assertEqual(reviewed["portfolio_metrics"][0]["evidence"]["review"]["status"], "approved")
        self.assertEqual(review_summary(reviewed), {
            "total": 2, "pending": 1, "approved": 1, "rejected": 0, "not_required": 0,
        })

    def test_browser_catalog_excludes_reviewer_note_and_private_source(self):
        record = fictional_supplement()
        candidate = next(iter(iter_supplement_evidence(record)))
        ledger = upsert_review(
            {"schema_version": "1.0", "updated_at": None, "reviews": []},
            evidence_identifier=candidate["evidence_id"], status="approved",
            reviewed_by="SECRET-REVIEWER", note="SECRET-NOTE",
        )
        payload = sanitized_pdf_catalog([record], ledger)
        rendered = json.dumps(payload)
        self.assertEqual(payload["meta"]["review_summary"]["approved"], 1)
        self.assertEqual(payload["supplements"][0]["portfolio_metrics"][0]["evidence"]["review"]["status"], "approved")
        for secret in ("SECRET-REVIEWER", "SECRET-NOTE", "SECRET-SHA", "SECRET.pdf", "doc-0123456789abcdefabcd"):
            self.assertNotIn(secret, rendered)

    def test_ledger_round_trip_and_schema_required_fields(self):
        schema = json.loads((ROOT / "schema/pdf-review-ledger.schema.json").read_text())
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "reviews.json"
            ledger = upsert_review(
                {"schema_version": "1.0", "updated_at": None, "reviews": []},
                evidence_identifier=evidence_id(fictional_evidence("occupancy_rate_percent", 98.5, 2)),
                status="not_required", reviewed_by="Fictional Reviewer",
            )
            save_review_ledger(path, ledger)
            loaded = load_review_ledger(path)
            self.assertEqual(set(schema["required"]) - set(loaded), set())
            self.assertEqual(loaded["reviews"][0]["status"], "not_required")

    def test_discovers_multiple_pdf_supplements(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            record = fictional_supplement()
            (directory / "fictional-earnings-presentation.json").write_text(json.dumps(record))
            (directory / "second-pdf-supplement.json").write_text(json.dumps(record))
            (directory / "properties.json").write_text(json.dumps(record))
            self.assertEqual(len(discover_supplement_paths(directory)), 2)
            self.assertEqual(len(load_pdf_supplements(directory)), 2)

    def test_prefix_resolution_rejects_unknown_and_ambiguous_ids(self):
        items = list(iter_supplement_evidence(fictional_supplement()))
        first = items[0]["evidence_id"]
        self.assertEqual(resolve_evidence_prefix(items, first[:12]), first)
        with self.assertRaises(ValueError):
            resolve_evidence_prefix(items, "ev-unknown")
        with self.assertRaises(ValueError):
            resolve_evidence_prefix([
                {"evidence_id": "ev-a"}, {"evidence_id": "ev-ab"},
            ], "ev-a")


if __name__ == "__main__":
    unittest.main()
