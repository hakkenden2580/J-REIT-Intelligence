#!/usr/bin/env python3
"""Serve the prototype on localhost without exposing private-data directories."""

from __future__ import annotations

import argparse
import functools
import io
import json
import posixpath
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlsplit

from data_engine.pdf_reviews import apply_review_ledger, load_review_ledger, review_summary
from data_engine.pdf_supplements import load_pdf_supplements
from runtime_paths import NORMALIZED_DIR, REPORTS_DIR, REVIEWS_DIR, ROOT, ensure_private_dirs

BLOCKED_PREFIXES = ("/private-data/", "/sources/raw/", "/.git/")
BLOCKED_DIRECTORIES = {"/private-data", "/sources/raw", "/.git"}
BLOCKED_LEGACY_FILES = {
    "/data/properties.json",
    "/data/nbf-properties.json",
    "/data/jre-properties.json",
    "/data/glp-properties.json",
    "/data/import-report.json",
    "/data/all-import-report.json",
    "/data/geocode-cache.json",
}


def normalized_request_path(raw_path: str) -> str:
    decoded = unquote(urlsplit(raw_path).path)
    return "/" + posixpath.normpath(decoded).lstrip("/")


def is_blocked_path(request_path: str) -> bool:
    return (
        request_path in BLOCKED_DIRECTORIES
        or request_path.startswith(BLOCKED_PREFIXES)
        or request_path in BLOCKED_LEGACY_FILES
        or request_path == "/.env"
        or request_path.startswith("/.env.")
    )


def sanitized_import_status(record: dict) -> dict:
    layout_values = set(record.get("layout_statuses", {}).values())
    layout_status = "changed" if "changed" in layout_values else "unchanged" if layout_values == {"unchanged"} else "new"
    return {
        "run_id": record.get("run_id"),
        "status": record.get("status"),
        "finished_at": record.get("finished_at"),
        "same_inputs": bool(record.get("same_inputs_as_run_id")),
        "layout_status": layout_status,
        "totals": record.get("totals", {}),
    }


def sanitized_quality_status(record: dict) -> dict:
    """Expose aggregate quality metrics without source or property-level details."""
    allowed_totals = (
        "properties", "periods", "numeric_values", "evidence_complete",
        "evidence_coverage_percent", "with_coordinates",
        "coordinate_coverage_percent", "duplicate_ids", "errors", "warnings",
    )
    totals = record.get("totals", {})
    metrics = {}
    for code, item in record.get("metrics", {}).items():
        metrics[code] = {
            "available": item.get("available", 0),
            "evidence_complete": item.get("evidence_complete", 0),
            "coverage_percent": item.get("coverage_percent", 0),
        }
    by_reit = {}
    for name, item in record.get("by_reit", {}).items():
        by_reit[name] = {
            "properties": item.get("properties", 0),
            "periods": item.get("periods", 0),
            "evidence_coverage_percent": item.get("evidence_coverage_percent", 0),
            "coordinate_coverage_percent": item.get("coordinate_coverage_percent", 0),
        }
    checks = [{key: item.get(key) for key in ("code", "severity", "status", "count", "message")}
              for item in record.get("checks", [])]
    return {
        "status": record.get("status"),
        "generated_at": record.get("generated_at"),
        "totals": {key: totals.get(key, 0) for key in allowed_totals},
        "by_reit": by_reit,
        "metrics": metrics,
        "checks": checks,
    }


def sanitized_change_status(record: dict) -> dict:
    """Expose change counts only; property names, IDs and Evidence stay private."""
    allowed_totals = (
        "previous_properties", "current_properties", "properties_added",
        "properties_removed", "properties_changed", "master_field_changes",
        "periods_added", "periods_removed", "metric_values_added",
        "metric_values_removed", "metric_values_changed", "evidence_relinked",
    )
    totals = record.get("totals", {})
    allowed_reit = (
        "properties_added", "properties_removed", "properties_changed",
        "periods_added", "periods_removed", "metric_values_added",
        "metric_values_removed", "metric_values_changed", "evidence_relinked",
    )
    by_reit = {
        name: {key: item.get(key, 0) for key in allowed_reit}
        for name, item in record.get("by_reit", {}).items()
    }
    by_metric = {
        code: {key: item.get(key, 0) for key in ("added", "removed", "changed", "evidence_relinked")}
        for code, item in record.get("by_metric", {}).items()
    }
    return {
        "status": record.get("status"),
        "generated_at": record.get("generated_at"),
        "totals": {key: totals.get(key, 0) for key in allowed_totals},
        "by_reit": by_reit,
        "by_metric": by_metric,
    }


def sanitized_pdf_supplement(record: dict) -> dict:
    """Expose selected PDF metrics without raw paths, hashes or download URLs."""
    meta = record.get("meta", {})
    raw_source = meta.get("source", {})
    source_url = raw_source.get("url", "")
    if not isinstance(source_url, str) or not source_url.startswith(("https://", "http://")):
        source_url = ""

    def evidence(item: dict) -> dict:
        locator = item.get("locator", {})
        extraction = item.get("extraction", {})
        review = item.get("review", {})
        return {
            "metric_code": item.get("metric_code"),
            "value": item.get("value"),
            "unit": item.get("unit"),
            "observed_at": item.get("observed_at"),
            "retrieved_at": item.get("retrieved_at"),
            "locator": {
                "type": locator.get("type"),
                "page": locator.get("page"),
                "bbox": locator.get("bbox"),
            },
            "extraction": {
                "parser": extraction.get("parser"),
                "parser_version": extraction.get("parser_version"),
                "method": extraction.get("method"),
                "confidence": extraction.get("confidence"),
            },
            "review": {"status": review.get("status")},
        }

    portfolio_metrics = [{
        "metric_code": item.get("metric_code"),
        "value": item.get("value"),
        "unit": item.get("unit"),
        "period": item.get("period"),
        "as_of_date": item.get("as_of_date"),
        "evidence": evidence(item.get("evidence", {})),
    } for item in record.get("portfolio_metrics", [])]
    property_events = [{
        "property_name": item.get("property_name"),
        "reit": item.get("reit"),
        "reit_code": item.get("reit_code"),
        "event_type": item.get("event_type"),
        "announced_period": item.get("announced_period"),
        "as_of_date": item.get("as_of_date"),
        "price_million_yen": item.get("price_million_yen"),
        "noi_yield_percent": item.get("noi_yield_percent"),
        "evidence": {key: evidence(value) for key, value in item.get("evidence", {}).items()},
    } for item in record.get("property_events", [])]
    return {
        "meta": {
            "dataset": meta.get("dataset"),
            "data_engine_version": meta.get("data_engine_version"),
            "publisher": meta.get("publisher"),
            "reit_code": meta.get("reit_code"),
            "period": meta.get("period"),
            "as_of_date": meta.get("as_of_date"),
            "notice": meta.get("notice"),
            "source": {
                "document": raw_source.get("document") or raw_source.get("title"),
                "period": raw_source.get("period"),
                "url": source_url,
                "retrieved_at": raw_source.get("retrieved_at"),
            },
        },
        "portfolio_metrics": portfolio_metrics,
        "property_events": property_events,
        "review_summary": review_summary(record),
    }


def sanitized_pdf_catalog(records: list[dict], ledger: dict) -> dict:
    supplements = [sanitized_pdf_supplement(apply_review_ledger(record, ledger)) for record in records]
    aggregate = {"total": 0, "pending": 0, "approved": 0, "rejected": 0, "not_required": 0}
    for supplement in supplements:
        for key in aggregate:
            aggregate[key] += int(supplement.get("review_summary", {}).get(key, 0))
    return {
        "meta": {
            "supplement_count": len(supplements),
            "event_count": sum(len(item.get("property_events", [])) for item in supplements),
            "review_summary": aggregate,
        },
        "supplements": supplements,
    }


class LocalHandler(SimpleHTTPRequestHandler):
    def json_response(self, payload: dict):
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        return io.BytesIO(encoded)

    def copyfile(self, source, outputfile) -> None:
        try:
            super().copyfile(source, outputfile)
        except BrokenPipeError:
            # A browser can cancel a large JSON response after reading headers.
            pass

    def send_head(self):
        request_path = normalized_request_path(self.path)
        if request_path == "/runtime-data/pdf-supplements.json":
            try:
                records = load_pdf_supplements(NORMALIZED_DIR)
                if not records:
                    self.send_error(404, "PDF supplements not found")
                    return None
                ledger = load_review_ledger(REVIEWS_DIR / "pdf-evidence-reviews.json")
                return self.json_response(sanitized_pdf_catalog(records, ledger))
            except (OSError, json.JSONDecodeError, TypeError, ValueError):
                self.send_error(500, "PDF supplements are invalid")
                return None
        if request_path == "/runtime-data/nbf-pdf.json":
            target = NORMALIZED_DIR / "nbf-49-earnings-presentation.json"
            if not target.is_file():
                self.send_error(404, "NBF PDF supplement not found")
                return None
            try:
                ledger = load_review_ledger(REVIEWS_DIR / "pdf-evidence-reviews.json")
                record = apply_review_ledger(json.loads(target.read_text(encoding="utf-8")), ledger)
                return self.json_response(sanitized_pdf_supplement(record))
            except (OSError, json.JSONDecodeError, TypeError, ValueError):
                self.send_error(500, "NBF PDF supplement is invalid")
                return None
        if request_path == "/runtime-data/change-status.json":
            target = REPORTS_DIR / "latest-change-report.json"
            if not target.is_file():
                self.send_error(404, "Change status not found")
                return None
            try:
                return self.json_response(sanitized_change_status(json.loads(target.read_text(encoding="utf-8"))))
            except (OSError, json.JSONDecodeError):
                self.send_error(500, "Change status is invalid")
                return None
        if request_path == "/runtime-data/quality-status.json":
            target = REPORTS_DIR / "latest-quality-report.json"
            if not target.is_file():
                self.send_error(404, "Quality status not found")
                return None
            try:
                return self.json_response(sanitized_quality_status(json.loads(target.read_text(encoding="utf-8"))))
            except (OSError, json.JSONDecodeError):
                self.send_error(500, "Quality status is invalid")
                return None
        if request_path == "/runtime-data/import-status.json":
            target = REPORTS_DIR / "latest-import-run.json"
            if not target.is_file():
                self.send_error(404, "Import status not found")
                return None
            try:
                return self.json_response(sanitized_import_status(json.loads(target.read_text(encoding="utf-8"))))
            except (OSError, json.JSONDecodeError):
                self.send_error(500, "Import status is invalid")
                return None
        if request_path == "/runtime-data/properties.json":
            target = NORMALIZED_DIR / "properties.json"
            if not target.is_file():
                self.send_error(404, "Local normalized data not found")
                return None
            stream = target.open("rb")
            size = target.stat().st_size
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(size))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            return stream
        if is_blocked_path(request_path):
            self.send_error(404, "Private runtime path is not publicly served")
            return None
        return super().send_head()

    def log_message(self, format_string: str, *args) -> None:
        super().log_message(format_string, *args)


class LocalServer(ThreadingHTTPServer):
    allow_reuse_address = True


def main() -> int:
    parser = argparse.ArgumentParser(description="J-REIT Intelligence local-only web server")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--bind", default="127.0.0.1", choices=["127.0.0.1", "::1"])
    args = parser.parse_args()
    ensure_private_dirs()
    handler = functools.partial(LocalHandler, directory=str(ROOT))
    server = LocalServer((args.bind, args.port), handler)
    print(json.dumps({
        "url": f"http://127.0.0.1:{args.port}",
        "bind": args.bind,
        "private_data": str(NORMALIZED_DIR.parent),
        "note": "Control+C で終了",
    }, ensure_ascii=False, indent=2))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n停止しました。")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
