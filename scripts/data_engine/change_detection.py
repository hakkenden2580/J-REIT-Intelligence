"""Semantic dataset diff and local snapshot retention.

The detailed report and compressed snapshots contain real property data and
must remain below ``private-data``.  Browser-facing code receives only the
aggregate form produced by ``sanitized_change_status`` in ``serve_local.py``.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from evidence import METRICS

MASTER_FIELDS = ("name", "reit", "reit_code", "type", "region", "address", "lat", "lng")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _period_key(record: dict[str, Any]) -> str:
    date = record.get("as_of_date") or "undated"
    label = record.get("period_no") if record.get("period_no") is not None else record.get("period") or "unlabelled"
    return f"{date}|{label}"


def _semantic_evidence(record: dict[str, Any]) -> dict[str, Any]:
    result = {}
    for metric, item in (record.get("evidence") or {}).items():
        if not isinstance(item, dict):
            continue
        locator = item.get("locator") or {}
        result[metric] = {
            "source_document_id": item.get("source_document_id"),
            "locator": {
                "type": locator.get("type"),
                "page": locator.get("page"),
                "sheet": locator.get("sheet"),
                "cell": locator.get("cell"),
                "cell_range": locator.get("cell_range"),
            },
        }
    return result


def _semantic_property(item: dict[str, Any]) -> dict[str, Any]:
    """Keep business values while excluding volatile source metadata."""
    return {
        "id": item.get("id"),
        "master": {field: item.get(field) for field in MASTER_FIELDS},
        "periods": [
            {
                "key": _period_key(period),
                "values": {field: period.get(field) for field in METRICS},
                "evidence": _semantic_evidence(period),
            }
            for period in sorted(item.get("periods") or [], key=_period_key)
        ],
    }


def semantic_fingerprint(payload: dict[str, Any] | None) -> str | None:
    if not payload:
        return None
    properties = sorted(
        (_semantic_property(item) for item in payload.get("properties") or []),
        key=lambda item: str(item.get("id") or ""),
    )
    encoded = json.dumps(properties, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _numeric_values(record: dict[str, Any]) -> dict[str, int | float]:
    return {
        field: value for field in METRICS
        if isinstance((value := record.get(field)), (int, float)) and not isinstance(value, bool)
    }


def _evidence_reference(record: dict[str, Any], metric: str) -> dict[str, Any] | None:
    evidence = (record.get("evidence") or {}).get(metric)
    if not isinstance(evidence, dict):
        return None
    locator = evidence.get("locator") or {}
    return {
        "source_document_id": evidence.get("source_document_id"),
        "retrieved_at": evidence.get("retrieved_at"),
        "locator": {
            "type": locator.get("type"),
            "page": locator.get("page"),
            "sheet": locator.get("sheet"),
            "cell": locator.get("cell"),
            "cell_range": locator.get("cell_range"),
        },
    }


def _empty_reit_summary() -> dict[str, int]:
    return {
        "properties_added": 0,
        "properties_removed": 0,
        "properties_changed": 0,
        "periods_added": 0,
        "periods_removed": 0,
        "metric_values_added": 0,
        "metric_values_removed": 0,
        "metric_values_changed": 0,
        "evidence_relinked": 0,
    }


def compare_datasets(
    previous: dict[str, Any] | None,
    current: dict[str, Any],
    *,
    import_run_id: str | None = None,
) -> dict[str, Any]:
    """Compare two normalized payloads and return a private, evidence-first report."""
    previous_fingerprint = semantic_fingerprint(previous)
    current_fingerprint = semantic_fingerprint(current)
    current_map = {str(item.get("id")): item for item in current.get("properties") or [] if item.get("id")}
    previous_map = {
        str(item.get("id")): item for item in (previous or {}).get("properties") or [] if item.get("id")
    }
    if previous is None:
        return {
            "schema_version": "1.0",
            "generated_at": _now(),
            "import_run_id": import_run_id,
            "previous_import_run_id": None,
            "status": "baseline",
            "previous_fingerprint": None,
            "current_fingerprint": current_fingerprint,
            "totals": {
                "previous_properties": 0,
                "current_properties": len(current_map),
                "properties_added": 0,
                "properties_removed": 0,
                "properties_changed": 0,
                "master_field_changes": 0,
                "periods_added": 0,
                "periods_removed": 0,
                "metric_values_added": 0,
                "metric_values_removed": 0,
                "metric_values_changed": 0,
                "evidence_relinked": 0,
            },
            "by_reit": {},
            "by_metric": {
                field: {"added": 0, "removed": 0, "changed": 0, "evidence_relinked": 0}
                for field in METRICS
            },
            "details": {
                "properties_added": [], "properties_removed": [], "master_changes": [],
                "periods_added": [], "periods_removed": [], "metric_changes": [],
                "evidence_relinked": [],
            },
        }
    added_ids = sorted(set(current_map) - set(previous_map))
    removed_ids = sorted(set(previous_map) - set(current_map))
    shared_ids = sorted(set(previous_map) & set(current_map))
    by_reit: dict[str, dict[str, int]] = defaultdict(_empty_reit_summary)
    by_metric: dict[str, dict[str, int]] = {
        field: {"added": 0, "removed": 0, "changed": 0, "evidence_relinked": 0}
        for field in METRICS
    }
    details: dict[str, list[dict[str, Any]]] = {
        "properties_added": [],
        "properties_removed": [],
        "master_changes": [],
        "periods_added": [],
        "periods_removed": [],
        "metric_changes": [],
        "evidence_relinked": [],
    }
    changed_property_ids: set[str] = set()

    def add_period_values(item: dict[str, Any], period: dict[str, Any], direction: str) -> None:
        reit = str(item.get("reit") or "未分類")
        values = _numeric_values(period)
        by_reit[reit][f"metric_values_{direction}"] += len(values)
        for metric in values:
            by_metric[metric][direction] += 1

    for identifier in added_ids:
        item = current_map[identifier]
        reit = str(item.get("reit") or "未分類")
        periods = item.get("periods") or []
        by_reit[reit]["properties_added"] += 1
        by_reit[reit]["periods_added"] += len(periods)
        for period in periods:
            add_period_values(item, period, "added")
        details["properties_added"].append({
            "property_id": identifier, "name": item.get("name"), "reit": reit,
            "periods": len(periods), "source_document_id": (item.get("source") or {}).get("document_id"),
        })

    for identifier in removed_ids:
        item = previous_map[identifier]
        reit = str(item.get("reit") or "未分類")
        periods = item.get("periods") or []
        by_reit[reit]["properties_removed"] += 1
        by_reit[reit]["periods_removed"] += len(periods)
        for period in periods:
            add_period_values(item, period, "removed")
        details["properties_removed"].append({
            "property_id": identifier, "name": item.get("name"), "reit": reit, "periods": len(periods),
        })

    for identifier in shared_ids:
        before, after = previous_map[identifier], current_map[identifier]
        reit = str(after.get("reit") or before.get("reit") or "未分類")
        property_changed = False
        for field in MASTER_FIELDS:
            if before.get(field) != after.get(field):
                property_changed = True
                details["master_changes"].append({
                    "property_id": identifier, "name": after.get("name") or before.get("name"),
                    "reit": reit, "field": field, "before": before.get(field), "after": after.get(field),
                })
        before_periods = {_period_key(item): item for item in before.get("periods") or []}
        after_periods = {_period_key(item): item for item in after.get("periods") or []}
        for key in sorted(set(after_periods) - set(before_periods)):
            property_changed = True
            period = after_periods[key]
            by_reit[reit]["periods_added"] += 1
            add_period_values(after, period, "added")
            details["periods_added"].append({
                "property_id": identifier, "name": after.get("name"), "reit": reit,
                "period": period.get("period"), "as_of_date": period.get("as_of_date"),
                "metrics": sorted(_numeric_values(period)),
            })
        for key in sorted(set(before_periods) - set(after_periods)):
            property_changed = True
            period = before_periods[key]
            by_reit[reit]["periods_removed"] += 1
            add_period_values(before, period, "removed")
            details["periods_removed"].append({
                "property_id": identifier, "name": before.get("name"), "reit": reit,
                "period": period.get("period"), "as_of_date": period.get("as_of_date"),
                "metrics": sorted(_numeric_values(period)),
            })
        for key in sorted(set(before_periods) & set(after_periods)):
            old_record, new_record = before_periods[key], after_periods[key]
            for metric in METRICS:
                old_value, new_value = old_record.get(metric), new_record.get(metric)
                if old_value != new_value:
                    property_changed = True
                    if old_value is None and isinstance(new_value, (int, float)):
                        direction = "added"
                    elif new_value is None and isinstance(old_value, (int, float)):
                        direction = "removed"
                    else:
                        direction = "changed"
                    by_reit[reit][f"metric_values_{direction}"] += 1
                    by_metric[metric][direction] += 1
                    details["metric_changes"].append({
                        "property_id": identifier, "name": after.get("name"), "reit": reit,
                        "period": new_record.get("period") or old_record.get("period"),
                        "as_of_date": new_record.get("as_of_date") or old_record.get("as_of_date"),
                        "metric": metric, "before": old_value, "after": new_value,
                        "delta": new_value - old_value if isinstance(old_value, (int, float)) and isinstance(new_value, (int, float)) else None,
                        "evidence": _evidence_reference(new_record, metric),
                    })
                elif isinstance(new_value, (int, float)):
                    old_evidence = _evidence_reference(old_record, metric)
                    new_evidence = _evidence_reference(new_record, metric)
                    old_document = (old_evidence or {}).get("source_document_id")
                    new_document = (new_evidence or {}).get("source_document_id")
                    if old_document and new_document and old_document != new_document:
                        property_changed = True
                        by_reit[reit]["evidence_relinked"] += 1
                        by_metric[metric]["evidence_relinked"] += 1
                        details["evidence_relinked"].append({
                            "property_id": identifier, "name": after.get("name"), "reit": reit,
                            "period": new_record.get("period"), "as_of_date": new_record.get("as_of_date"),
                            "metric": metric, "before": old_evidence, "after": new_evidence,
                        })
        if property_changed:
            changed_property_ids.add(identifier)
            by_reit[reit]["properties_changed"] += 1

    totals = {
        "previous_properties": len(previous_map),
        "current_properties": len(current_map),
        "properties_added": len(added_ids),
        "properties_removed": len(removed_ids),
        "properties_changed": len(changed_property_ids),
        "master_field_changes": len(details["master_changes"]),
        "periods_added": sum(item["periods_added"] for item in by_reit.values()),
        "periods_removed": sum(item["periods_removed"] for item in by_reit.values()),
        "metric_values_added": sum(item["metric_values_added"] for item in by_reit.values()),
        "metric_values_removed": sum(item["metric_values_removed"] for item in by_reit.values()),
        "metric_values_changed": sum(item["metric_values_changed"] for item in by_reit.values()),
        "evidence_relinked": sum(item["evidence_relinked"] for item in by_reit.values()),
    }
    changed = any(totals[key] for key in (
        "properties_added", "properties_removed", "properties_changed", "periods_added", "periods_removed",
        "metric_values_added", "metric_values_removed", "metric_values_changed", "evidence_relinked",
    ))
    status = "baseline" if previous is None else "changed" if changed else "unchanged"
    return {
        "schema_version": "1.0",
        "generated_at": _now(),
        "import_run_id": import_run_id,
        "previous_import_run_id": (previous or {}).get("meta", {}).get("import_run_id"),
        "status": status,
        "previous_fingerprint": previous_fingerprint,
        "current_fingerprint": current_fingerprint,
        "totals": totals,
        "by_reit": {name: values for name, values in sorted(by_reit.items())},
        "by_metric": by_metric,
        "details": details,
    }


def archive_snapshot(payload: dict[str, Any], snapshot_dir: Path, *, keep: int = 12) -> Path:
    """Store one gzip-compressed copy per semantic fingerprint and prune oldest copies."""
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    fingerprint = semantic_fingerprint(payload)
    if not fingerprint:
        raise ValueError("Cannot snapshot an empty dataset")
    path = snapshot_dir / f"properties-{fingerprint[:20]}.json.gz"
    if not path.exists():
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        with path.open("wb") as raw:
            with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as stream:
                stream.write(encoded)
    snapshots = sorted(snapshot_dir.glob("properties-*.json.gz"), key=lambda item: item.stat().st_mtime, reverse=True)
    for stale in snapshots[max(keep, 1):]:
        stale.unlink()
    return path
