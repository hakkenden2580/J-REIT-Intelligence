#!/usr/bin/env python3
"""Evidence-first helpers shared by the local Excel importers."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

PARSER_VERSION = "0.9.0"

METRICS = {
    "price": ("acquisition_price_million_yen", "million_jpy"),
    "book_value": ("book_value_million_yen", "million_jpy"),
    "appraisal": ("appraisal_value_million_yen", "million_jpy"),
    "leasable_area": ("leasable_area_sqm", "sqm"),
    "leased_area": ("leased_area_sqm", "sqm"),
    "tenants": ("tenant_count", "count"),
    "occupancy": ("occupancy_rate_percent", "percent"),
    "cap": ("cap_rate_percent", "percent"),
    "discount_rate": ("discount_rate_percent", "percent"),
    "terminal_cap_rate": ("terminal_cap_rate_percent", "percent"),
    "noi": ("noi_million_yen", "million_jpy"),
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def retrieved_at(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()


def source_document(
    path: Path,
    *,
    publisher: str,
    title: str,
    period: str,
    as_of_date: str,
    url: str,
    download_url: str,
    media_type: str = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
) -> dict:
    checksum = sha256_file(path)
    return {
        "document_id": f"doc-{checksum[:20]}",
        "publisher": publisher,
        "document": title,
        "title": title,
        "period": period,
        "as_of_date": as_of_date,
        "url": url,
        "download_url": download_url,
        "sha256": checksum,
        "retrieved_at": retrieved_at(path),
        "media_type": media_type,
    }


def excel_locator(reference: str | None) -> dict | None:
    if not reference or "!" not in reference:
        return None
    sheet, cell = reference.rsplit("!", 1)
    return {
        "type": "excel_cell",
        "page": None,
        "sheet": sheet,
        "cell": cell,
        "cell_range": cell,
        "bbox": None,
    }


def pdf_locator(page: int, bbox: tuple[float, float, float, float] | list[float]) -> dict:
    if page < 1:
        raise ValueError("PDF page number must be 1-based")
    if len(bbox) != 4:
        raise ValueError("PDF bbox must contain four coordinates")
    return {
        "type": "pdf_bbox",
        "page": page,
        "sheet": None,
        "cell": None,
        "cell_range": None,
        "bbox": [round(float(value), 2) for value in bbox],
    }


def pdf_metric_evidence(
    *,
    field: str,
    value: float,
    observed_at: str | None,
    source: dict,
    page: int,
    bbox: tuple[float, float, float, float] | list[float],
    parser_name: str,
    confidence: float,
) -> dict:
    metric_code, unit = METRICS[field]
    return {
        "metric_code": metric_code,
        "value": value,
        "unit": unit,
        "observed_at": observed_at,
        "source_document_id": source["document_id"],
        "retrieved_at": source["retrieved_at"],
        "locator": pdf_locator(page, bbox),
        "extraction": {
            "parser": parser_name,
            "parser_version": PARSER_VERSION,
            "method": "deterministic_pdf_text",
            "confidence": confidence,
        },
        "review": {
            "status": "pending",
            "reviewed_by": None,
            "reviewed_at": None,
        },
    }


def metric_evidence(
    record: dict,
    source: dict,
    cells: dict[str, str | None],
    *,
    parser_name: str,
) -> dict:
    result = {}
    for field, (metric_code, unit) in METRICS.items():
        value = record.get(field)
        locator = excel_locator(cells.get(field))
        if value is None or locator is None:
            continue
        result[field] = {
            "metric_code": metric_code,
            "value": value,
            "unit": unit,
            "observed_at": record.get("as_of_date"),
            "source_document_id": source["document_id"],
            "retrieved_at": source["retrieved_at"],
            "locator": locator,
            "extraction": {
                "parser": parser_name,
                "parser_version": PARSER_VERSION,
                "method": "deterministic_xlsx_xml",
                "confidence": 1.0,
            },
            "review": {
                "status": "pending",
                "reviewed_by": None,
                "reviewed_at": None,
            },
        }
    return result
