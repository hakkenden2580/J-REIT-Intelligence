"""Local-only human review ledger for PDF Evidence."""

from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

REVIEW_STATUSES = {"approved", "rejected", "not_required"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def evidence_id(evidence: dict) -> str:
    """Create a stable ID without depending on reviewer or extraction timestamps."""
    locator = evidence.get("locator", {})
    payload = {
        "source_document_id": evidence.get("source_document_id"),
        "metric_code": evidence.get("metric_code"),
        "value": evidence.get("value"),
        "unit": evidence.get("unit"),
        "observed_at": evidence.get("observed_at"),
        "locator": {
            "type": locator.get("type"),
            "page": locator.get("page"),
            "sheet": locator.get("sheet"),
            "cell": locator.get("cell"),
            "cell_range": locator.get("cell_range"),
            "bbox": locator.get("bbox"),
        },
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"ev-{hashlib.sha256(encoded).hexdigest()[:32]}"


def iter_supplement_evidence(record: dict):
    for metric in record.get("portfolio_metrics", []):
        evidence = metric.get("evidence")
        if isinstance(evidence, dict) and evidence.get("metric_code"):
            yield {
                "evidence_id": evidence_id(evidence),
                "context_type": "portfolio_metric",
                "context_label": metric.get("metric_code"),
                "evidence": evidence,
            }
    for event in record.get("property_events", []):
        for field, evidence in event.get("evidence", {}).items():
            if isinstance(evidence, dict) and evidence.get("metric_code"):
                yield {
                    "evidence_id": evidence_id(evidence),
                    "context_type": "property_event",
                    "context_label": event.get("property_name"),
                    "field": field,
                    "event_type": event.get("event_type"),
                    "evidence": evidence,
                }


def empty_ledger() -> dict:
    return {"schema_version": "1.0", "updated_at": None, "reviews": []}


def load_review_ledger(path: Path) -> dict:
    if not path.is_file():
        return empty_ledger()
    record = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(record, dict) or not isinstance(record.get("reviews"), list):
        raise ValueError("PDF review ledger has an invalid structure")
    return record


def save_review_ledger(path: Path, ledger: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ledger = copy.deepcopy(ledger)
    ledger["schema_version"] = "1.0"
    ledger["updated_at"] = utc_now()
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def review_index(ledger: dict) -> dict[str, dict]:
    return {
        item["evidence_id"]: item
        for item in ledger.get("reviews", [])
        if isinstance(item, dict) and item.get("evidence_id")
    }


def apply_review_ledger(record: dict, ledger: dict) -> dict:
    reviewed = copy.deepcopy(record)
    index = review_index(ledger)
    for candidate in iter_supplement_evidence(reviewed):
        item = index.get(candidate["evidence_id"])
        if not item:
            continue
        candidate["evidence"]["review"] = {
            "status": item.get("status", "pending"),
            "reviewed_by": item.get("reviewed_by"),
            "reviewed_at": item.get("reviewed_at"),
        }
    return reviewed


def review_summary(record: dict) -> dict:
    summary = {"total": 0, "pending": 0, "approved": 0, "rejected": 0, "not_required": 0}
    for candidate in iter_supplement_evidence(record):
        status = candidate["evidence"].get("review", {}).get("status", "pending")
        if status not in summary:
            status = "pending"
        summary["total"] += 1
        summary[status] += 1
    return summary


def upsert_review(
    ledger: dict,
    *,
    evidence_identifier: str,
    status: str,
    reviewed_by: str,
    note: str | None = None,
) -> dict:
    if status not in REVIEW_STATUSES:
        raise ValueError(f"Unsupported review status: {status}")
    if not reviewed_by.strip():
        raise ValueError("reviewed_by must not be blank")
    result = copy.deepcopy(ledger)
    reviews = [item for item in result.get("reviews", []) if item.get("evidence_id") != evidence_identifier]
    reviews.append({
        "evidence_id": evidence_identifier,
        "status": status,
        "reviewed_by": reviewed_by.strip(),
        "reviewed_at": utc_now(),
        "note": note.strip() if note else None,
    })
    result["reviews"] = sorted(reviews, key=lambda item: item["evidence_id"])
    return result


def clear_review(ledger: dict, evidence_identifier: str) -> dict:
    result = copy.deepcopy(ledger)
    result["reviews"] = [item for item in result.get("reviews", []) if item.get("evidence_id") != evidence_identifier]
    return result


def resolve_evidence_prefix(candidates: list[dict], prefix: str) -> str:
    matches = sorted({item["evidence_id"] for item in candidates if item["evidence_id"].startswith(prefix)})
    if not matches:
        raise ValueError(f"Evidence ID not found: {prefix}")
    if len(matches) > 1:
        raise ValueError(f"Evidence ID prefix is ambiguous: {prefix}")
    return matches[0]
