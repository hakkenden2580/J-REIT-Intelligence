"""Deterministic data-quality gates for normalized property datasets.

The detailed report is written below ``private-data/reports``.  Browser-facing
code receives only the aggregate form produced by ``sanitized_quality_report``
in ``serve_local.py``.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any

from evidence import METRICS

CORE_FIELDS = ("id", "reit", "reit_code", "name", "type", "address")
PERCENT_METRICS = ("occupancy", "cap", "discount_rate", "terminal_cap_rate")
NON_NEGATIVE_METRICS = (
    "price", "book_value", "appraisal", "leasable_area", "leased_area", "tenants"
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _percent(numerator: int, denominator: int) -> float:
    return round(numerator / denominator * 100, 1) if denominator else 100.0


def _evidence_complete(item: dict[str, Any] | None) -> bool:
    if not isinstance(item, dict):
        return False
    locator = item.get("locator") or {}
    extraction = item.get("extraction") or {}
    has_location = bool(locator.get("page") or locator.get("sheet")) and bool(
        locator.get("page") or locator.get("cell") or locator.get("cell_range")
    )
    return bool(
        item.get("source_document_id")
        and item.get("retrieved_at")
        and item.get("metric_code")
        and item.get("unit")
        and has_location
        and extraction.get("parser")
        and extraction.get("parser_version")
    )


def evaluate_dataset(payload: dict[str, Any], *, import_run_id: str | None = None) -> dict[str, Any]:
    """Return an aggregate report plus private issue samples for local review."""
    properties = payload.get("properties") or []
    identifiers = [item.get("id") for item in properties if item.get("id")]
    duplicates = sorted(key for key, count in Counter(identifiers).items() if count > 1)
    core_missing: list[dict[str, str]] = []
    invalid_coordinates: list[str] = []
    missing_coordinates: list[str] = []
    out_of_range: list[dict[str, Any]] = []
    area_mismatches: list[str] = []
    metric_counts: dict[str, dict[str, int]] = {
        field: {"available": 0, "evidence_complete": 0} for field in METRICS
    }
    by_reit: dict[str, dict[str, int]] = defaultdict(
        lambda: {"properties": 0, "periods": 0, "numeric_values": 0, "evidence_complete": 0, "with_coordinates": 0}
    )
    total_periods = 0

    def inspect_record(record: dict[str, Any], property_id: str, reit: str) -> None:
        evidence = record.get("evidence") or {}
        for field in METRICS:
            value = record.get(field)
            if value is None or isinstance(value, bool) or not isinstance(value, (int, float)):
                continue
            metric_counts[field]["available"] += 1
            by_reit[reit]["numeric_values"] += 1
            if _evidence_complete(evidence.get(field)):
                metric_counts[field]["evidence_complete"] += 1
                by_reit[reit]["evidence_complete"] += 1
            if field == "occupancy" and not 0 <= value <= 100:
                out_of_range.append({"property_id": property_id, "metric": field, "value": value})
            elif field in PERCENT_METRICS[1:] and not 0 < value <= 20:
                out_of_range.append({"property_id": property_id, "metric": field, "value": value})
            elif field in NON_NEGATIVE_METRICS and value < 0:
                out_of_range.append({"property_id": property_id, "metric": field, "value": value})
        leasable, leased = record.get("leasable_area"), record.get("leased_area")
        if isinstance(leasable, (int, float)) and isinstance(leased, (int, float)) and leased > leasable * 1.02:
            area_mismatches.append(property_id)

    for item in properties:
        property_id = str(item.get("id") or "unknown")
        reit = str(item.get("reit") or "未分類")
        by_reit[reit]["properties"] += 1
        missing = [field for field in CORE_FIELDS if not item.get(field)]
        if missing:
            core_missing.append({"property_id": property_id, "fields": ",".join(missing)})
        lat, lng = item.get("lat"), item.get("lng")
        if lat is None or lng is None:
            missing_coordinates.append(property_id)
        elif not isinstance(lat, (int, float)) or not isinstance(lng, (int, float)) or not (-90 <= lat <= 90 and -180 <= lng <= 180):
            invalid_coordinates.append(property_id)
        else:
            by_reit[reit]["with_coordinates"] += 1
        inspect_record(item, property_id, reit)
        periods = item.get("periods") or []
        total_periods += len(periods)
        by_reit[reit]["periods"] += len(periods)
        for period in periods:
            inspect_record(period, property_id, reit)

    numeric_values = sum(value["available"] for value in metric_counts.values())
    evidence_complete = sum(value["evidence_complete"] for value in metric_counts.values())
    evidence_missing = numeric_values - evidence_complete
    errors = len(duplicates) + len(core_missing) + len(invalid_coordinates) + len(out_of_range) + evidence_missing
    warnings = len(missing_coordinates) + len(area_mismatches)
    status = "failed" if errors else "warning" if warnings else "passed"

    metrics = {
        field: {
            **counts,
            "coverage_percent": _percent(counts["evidence_complete"], counts["available"]),
        }
        for field, counts in metric_counts.items()
    }
    reit_summary = {
        name: {
            **counts,
            "evidence_coverage_percent": _percent(counts["evidence_complete"], counts["numeric_values"]),
            "coordinate_coverage_percent": _percent(counts["with_coordinates"], counts["properties"]),
        }
        for name, counts in sorted(by_reit.items())
    }
    checks = [
        {"code": "unique_property_id", "severity": "error", "status": "passed" if not duplicates else "failed", "count": len(duplicates), "message": "物件IDの重複"},
        {"code": "required_fields", "severity": "error", "status": "passed" if not core_missing else "failed", "count": len(core_missing), "message": "必須項目の欠損"},
        {"code": "numeric_ranges", "severity": "error", "status": "passed" if not out_of_range else "failed", "count": len(out_of_range), "message": "数値範囲の異常"},
        {"code": "evidence_completeness", "severity": "error", "status": "passed" if not evidence_missing else "failed", "count": evidence_missing, "message": "Evidenceが不完全な数値"},
        {"code": "coordinates", "severity": "warning", "status": "passed" if not (missing_coordinates or invalid_coordinates) else "warning", "count": len(missing_coordinates) + len(invalid_coordinates), "message": "座標の欠損または異常"},
        {"code": "leased_area_consistency", "severity": "warning", "status": "passed" if not area_mismatches else "warning", "count": len(area_mismatches), "message": "賃貸面積が賃貸可能面積を超過"},
    ]
    return {
        "schema_version": "1.0",
        "generated_at": _now(),
        "import_run_id": import_run_id,
        "status": status,
        "totals": {
            "properties": len(properties),
            "periods": total_periods,
            "numeric_values": numeric_values,
            "evidence_complete": evidence_complete,
            "evidence_coverage_percent": _percent(evidence_complete, numeric_values),
            "with_coordinates": sum(value["with_coordinates"] for value in by_reit.values()),
            "coordinate_coverage_percent": _percent(sum(value["with_coordinates"] for value in by_reit.values()), len(properties)),
            "duplicate_ids": len(duplicates),
            "errors": errors,
            "warnings": warnings,
        },
        "by_reit": reit_summary,
        "metrics": metrics,
        "checks": checks,
        "issue_samples": {
            "duplicate_ids": duplicates[:20],
            "core_missing": core_missing[:20],
            "invalid_coordinates": invalid_coordinates[:20],
            "missing_coordinates": missing_coordinates[:20],
            "out_of_range": out_of_range[:20],
            "area_mismatches": area_mismatches[:20],
        },
    }
