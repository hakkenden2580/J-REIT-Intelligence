"""Import Run orchestration, idempotency keys and local audit reports."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .contracts import AdapterResult, ImportContext, SourceAdapter


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _digest(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _previous_success(run_dir: Path, idempotency_key: str) -> str | None:
    for path in sorted(run_dir.glob("run-*.json"), reverse=True):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if record.get("status") == "succeeded" and record.get("idempotency_key") == idempotency_key:
            return record.get("run_id")
    return None


def _update_layout_baselines(context: ImportContext, results: list[AdapterResult]) -> dict[str, str]:
    path = context.reports_dir / "layout-baselines.json"
    baselines = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    statuses: dict[str, str] = {}
    for result in results:
        for layout in result.layout_reports:
            key = f"{result.adapter_id}:{layout['local_filename']}"
            previous = baselines.get(key)
            current = layout["fingerprint"]
            statuses[key] = "new" if previous is None else "unchanged" if previous == current else "changed"
            baselines[key] = current
    path.write_text(json.dumps(baselines, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return statuses


def execute_import_run(
    adapters: list[SourceAdapter],
    context: ImportContext,
) -> tuple[dict[str, AdapterResult], dict[str, Any]]:
    started_at = _now()
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    run_id = f"run-{timestamp}"
    run_dir = context.reports_dir / "import-runs"
    run_dir.mkdir(parents=True, exist_ok=True)
    results: dict[str, AdapterResult] = {}
    summaries: list[dict[str, Any]] = []
    try:
        for adapter in adapters:
            result = adapter.run(context)
            results[adapter.source_key] = result
            summaries.append(result.run_summary())
    except Exception as exc:
        failed = {
            "schema_version": "1.0",
            "run_id": run_id,
            "status": "failed",
            "started_at": started_at,
            "finished_at": _now(),
            "adapters": summaries,
            "error": {"type": type(exc).__name__, "message": str(exc)},
        }
        (run_dir / f"{run_id}.json").write_text(json.dumps(failed, ensure_ascii=False, indent=2), encoding="utf-8")
        (context.quarantine_dir / f"{run_id}.json").write_text(json.dumps(failed, ensure_ascii=False, indent=2), encoding="utf-8")
        raise
    identity = [{
        "adapter_id": item.adapter_id,
        "adapter_version": item.adapter_version,
        "sources": [{"sha256": asset.sha256, "layout_fingerprint": asset.layout_fingerprint}
                    for asset in item.source_assets],
    } for item in results.values()]
    idempotency_key = _digest(identity)
    reused_from = _previous_success(run_dir, idempotency_key)
    layout_statuses = _update_layout_baselines(context, list(results.values()))
    record = {
        "schema_version": "1.0",
        "run_id": run_id,
        "status": "succeeded",
        "started_at": started_at,
        "finished_at": _now(),
        "idempotency_key": idempotency_key,
        "same_inputs_as_run_id": reused_from,
        "adapters": summaries,
        "layout_statuses": layout_statuses,
        "totals": {
            "adapters": len(results),
            "properties": sum(len(result.payload.get("properties", [])) for result in results.values()),
            "issues": sum(len(result.issues) for result in results.values()),
        },
    }
    (run_dir / f"{run_id}.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    (context.reports_dir / "latest-import-run.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return results, record
