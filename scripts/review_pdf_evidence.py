#!/usr/bin/env python3
"""List and record human review decisions for local PDF Evidence."""

from __future__ import annotations

import argparse
import json

from data_engine.pdf_reviews import (
    REVIEW_STATUSES,
    clear_review,
    iter_supplement_evidence,
    load_review_ledger,
    resolve_evidence_prefix,
    save_review_ledger,
    upsert_review,
)
from data_engine.pdf_supplements import load_pdf_supplements
from runtime_paths import NORMALIZED_DIR, REVIEWS_DIR, ensure_private_dirs

LEDGER_PATH = REVIEWS_DIR / "pdf-evidence-reviews.json"


def candidates() -> list[dict]:
    result = []
    for record in load_pdf_supplements(NORMALIZED_DIR):
        source = record.get("meta", {}).get("source", {})
        document = source.get("document") or source.get("title") or "PDF"
        publisher = record.get("meta", {}).get("publisher") or ""
        for item in iter_supplement_evidence(record):
            result.append({**item, "document": document, "publisher": publisher})
    return result


def list_command(items: list[dict], ledger: dict) -> int:
    reviews = {item["evidence_id"]: item for item in ledger.get("reviews", [])}
    rows = []
    for item in items:
        evidence = item["evidence"]
        review = reviews.get(item["evidence_id"], evidence.get("review", {}))
        rows.append({
            "evidence_id": item["evidence_id"],
            "status": review.get("status", "pending"),
            "publisher": item["publisher"],
            "document": item["document"],
            "context": item["context_label"],
            "metric_code": evidence.get("metric_code"),
            "value": evidence.get("value"),
            "unit": evidence.get("unit"),
            "page": evidence.get("locator", {}).get("page"),
        })
    print(json.dumps({"evidence": rows, "count": len(rows)}, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Review local PDF Evidence without modifying source JSON")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("list", help="List PDF Evidence and current review status")

    set_parser = subparsers.add_parser("set", help="Approve, reject or mark Evidence as not required")
    set_parser.add_argument("evidence_id", help="Full Evidence ID or unique prefix")
    set_parser.add_argument("--status", required=True, choices=sorted(REVIEW_STATUSES))
    set_parser.add_argument("--reviewed-by", required=True)
    set_parser.add_argument("--note")

    clear_parser = subparsers.add_parser("clear", help="Remove a review decision and return to pending")
    clear_parser.add_argument("evidence_id", help="Full Evidence ID or unique prefix")

    args = parser.parse_args()
    ensure_private_dirs()
    items = candidates()
    ledger = load_review_ledger(LEDGER_PATH)

    if args.command == "list":
        return list_command(items, ledger)

    resolved = resolve_evidence_prefix(items, args.evidence_id)
    if args.command == "set":
        ledger = upsert_review(
            ledger,
            evidence_identifier=resolved,
            status=args.status,
            reviewed_by=args.reviewed_by,
            note=args.note,
        )
        action = args.status
    else:
        ledger = clear_review(ledger, resolved)
        action = "pending"
    save_review_ledger(LEDGER_PATH, ledger)
    print(json.dumps({
        "status": "succeeded",
        "evidence_id": resolved,
        "review_status": action,
        "private_ledger": str(LEDGER_PATH),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
