"""NBF earnings-presentation parser with page/bbox Evidence.

The normalized payload is supplemental: it does not overwrite the accepted
234-property Excel dataset. Raw text is kept in memory and never written to a
report or browser endpoint.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from evidence import pdf_value_evidence, source_document

from .pdf import require_pdf_dependencies

try:
    import pdfplumber
except ImportError:  # pragma: no cover
    pdfplumber = None


NUMBER_TOKEN = re.compile(r"^[▲△+\-]?\d[\d,]*(?:\.\d+)?(?:%|％|pt|億円|百万円)?$")


@dataclass(frozen=True)
class LocatedNumber:
    value: float
    raw: str
    bbox: tuple[float, float, float, float]


def _bbox(item: dict[str, Any]) -> tuple[float, float, float, float]:
    return (float(item["x0"]), float(item["top"]), float(item["x1"]), float(item["bottom"]))


def _center(item: dict[str, Any]) -> tuple[float, float]:
    return ((float(item["x0"]) + float(item["x1"])) / 2, (float(item["top"]) + float(item["bottom"])) / 2)


def _distance(left: dict[str, Any], right: dict[str, Any]) -> float:
    lx, ly = _center(left)
    rx, ry = _center(right)
    return math.hypot(lx - rx, ly - ry)


def _numeric_value(raw: str) -> float | None:
    compact = raw.strip().replace(" ", "").replace(",", "")
    if not NUMBER_TOKEN.match(compact):
        return None
    negative = compact.startswith(("▲", "△", "-"))
    match = re.search(r"\d+(?:\.\d+)?", compact)
    if not match:
        return None
    value = float(match.group())
    return -value if negative else value


def _search(page: Any, needle: str) -> list[dict[str, Any]]:
    return list(page.search(re.escape(needle), regex=True, case=True) or [])


def _find_page(pdf: Any, anchors: Iterable[str]) -> tuple[int, Any]:
    anchors = tuple(anchors)
    for page_number, page in enumerate(pdf.pages, 1):
        text = page.extract_text() or ""
        if all(anchor in text for anchor in anchors):
            return page_number, page
    raise ValueError(f"PDF page not found for anchors: {anchors}")


def _same_row_numbers(page: Any, labels: str | Iterable[str], *, value_index: int) -> LocatedNumber:
    labels = (labels,) if isinstance(labels, str) else tuple(labels)
    label_matches = [item for label in labels for item in _search(page, label)]
    if not label_matches:
        raise ValueError(f"PDF label not found: {' / '.join(labels)}")
    words = page.extract_words() or []
    compatible_rows = []
    for label_box in label_matches:
        label_y = _center(label_box)[1]
        candidates = []
        for word in words:
            value = _numeric_value(str(word.get("text", "")))
            if value is None or float(word["x0"]) <= float(label_box["x1"]):
                continue
            if abs(_center(word)[1] - label_y) <= 5.5:
                candidates.append((float(word["x0"]), value, word))
        candidates.sort(key=lambda item: item[0])
        if value_index < len(candidates):
            compatible_rows.append((len(candidates), -float(label_box["x0"]), candidates))
    if not compatible_rows:
        raise ValueError(f"PDF row has too few numeric values: {' / '.join(labels)}")
    # The P/L table and its explanatory notes can repeat a label. Prefer the
    # row with the richest numeric series, then the left-most table row.
    _, _, candidates = max(compatible_rows, key=lambda item: (item[0], item[1]))
    _, value, word = candidates[value_index]
    return LocatedNumber(value, str(word["text"]), _bbox(word))


def _nearest_label_number(page: Any, property_anchor: str, labels: Iterable[str]) -> LocatedNumber:
    anchors = _search(page, property_anchor)
    if not anchors:
        raise ValueError(f"PDF property anchor not found: {property_anchor}")
    anchor = anchors[0]
    label_matches = [item for label in labels for item in _search(page, label)]
    if not label_matches:
        raise ValueError(f"PDF metric label not found near: {property_anchor}")
    label_box = min(label_matches, key=lambda item: _distance(anchor, item))
    label_y = _center(label_box)[1]
    candidates: list[tuple[float, float, dict[str, Any]]] = []
    for word in page.extract_words() or []:
        value = _numeric_value(str(word.get("text", "")))
        if value is None:
            continue
        word_y = _center(word)[1]
        same_row = abs(word_y - label_y) <= 6 and float(word["x0"]) >= float(label_box["x1"]) - 2
        next_row = 0 < word_y - label_y <= 24 and abs(_center(word)[0] - _center(label_box)[0]) <= 80
        if not (same_row or next_row):
            continue
        row_penalty = 0 if same_row else 80
        candidates.append((row_penalty + _distance(label_box, word), value, word))
    if not candidates:
        raise ValueError(f"PDF value not found near {property_anchor}")
    _, value, word = min(candidates, key=lambda item: item[0])
    return LocatedNumber(value, str(word["text"]), _bbox(word))


def parse_nbf_earnings_presentation(path: Path, config: dict, layout: dict) -> tuple[dict, dict]:
    """Extract selected NBF portfolio metrics and property transactions."""
    require_pdf_dependencies()
    source = source_document(
        path,
        publisher=config["publisher"],
        title=config["title"],
        period=config["period"],
        as_of_date=config["as_of_date"],
        url=config["url"],
        download_url=config["download_url"],
        media_type="application/pdf",
    )
    portfolio_metrics = []
    property_events = []
    issues: list[dict[str, Any]] = []
    with pdfplumber.open(path) as pdf:
        summary_page_no, summary_page = _find_page(pdf, config["summary_anchors"])
        for item in config.get("portfolio_metrics", []):
            try:
                labels = item.get("labels") or [item["label"]]
                located = _same_row_numbers(summary_page, labels, value_index=int(item["value_index"]))
                value = located.value * float(item.get("multiplier", 1))
                portfolio_metrics.append({
                    "metric_code": item["metric_code"],
                    "value": value,
                    "unit": item["unit"],
                    "period": config["period"],
                    "as_of_date": config["as_of_date"],
                    "evidence": pdf_value_evidence(
                        metric_code=item["metric_code"], unit=item["unit"], value=value,
                        observed_at=config["as_of_date"], source=source,
                        page=summary_page_no, bbox=located.bbox,
                        parser_name="nbf_earnings_pdf", confidence=0.98,
                    ),
                })
            except ValueError as exc:
                issues.append({"scope": "portfolio", "metric_code": item["metric_code"], "message": str(exc)})

        growth_page_no, growth_page = _find_page(pdf, config["growth_anchors"])
        for event in config.get("property_events", []):
            record = {
                "property_name": event["property_name"],
                "reit": config["publisher"],
                "reit_code": config["reit_code"],
                "event_type": event["event_type"],
                "announced_period": config["period"],
                "as_of_date": config["as_of_date"],
                "evidence": {},
            }
            for metric in event.get("metrics", []):
                try:
                    located = _nearest_label_number(growth_page, event["anchor"], metric["labels"])
                    value = located.value * float(metric.get("multiplier", 1))
                    record[metric["field"]] = value
                    record["evidence"][metric["field"]] = pdf_value_evidence(
                        metric_code=metric["metric_code"], unit=metric["unit"], value=value,
                        observed_at=config["as_of_date"], source=source,
                        page=growth_page_no, bbox=located.bbox,
                        parser_name="nbf_earnings_pdf", confidence=0.9,
                    )
                except ValueError as exc:
                    issues.append({
                        "scope": "property_event", "event_index": len(property_events),
                        "metric_code": metric["metric_code"], "message": str(exc),
                    })
            if record["evidence"]:
                property_events.append(record)

    payload = {
        "meta": {
            "dataset": "nbf-earnings-presentation-pdf-local",
            "data_engine_version": "0.10.1",
            "publisher": config["publisher"],
            "reit_code": config["reit_code"],
            "period": config["period"],
            "as_of_date": config["as_of_date"],
            "source": source,
            "layout_fingerprint": layout["fingerprint"],
            "notice": "利用者のMac内で変換した補足データ。公開・再配布しないでください。",
        },
        "portfolio_metrics": portfolio_metrics,
        "property_events": property_events,
    }
    report = {
        "portfolio_metrics": len(portfolio_metrics),
        "property_events": len(property_events),
        "evidence_records": len(portfolio_metrics) + sum(len(item["evidence"]) for item in property_events),
        "issues": issues,
    }
    return payload, report
