"""Privacy-safe PDF inspection and page-level extraction primitives.

Raw text and tables returned by this module are process-local.  Layout reports
contain counts and dimensions only, so they can be used for drift detection
without copying source content into Git or a browser endpoint.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

try:
    import pdfplumber
except ImportError:  # pragma: no cover - exercised by the dependency message
    pdfplumber = None


PDF_MEDIA_TYPE = "application/pdf"
NUMBER_PATTERN = re.compile(r"[-+]?\d[\d,]*(?:\.\d+)?")


class PdfDependencyError(RuntimeError):
    """Raised when the optional PDF dependency set is unavailable."""


@dataclass(frozen=True)
class PdfTextMatch:
    page: int
    text: str
    bbox: tuple[float, float, float, float]


def require_pdf_dependencies() -> None:
    if pdfplumber is None:
        raise PdfDependencyError(
            "PDF機能にはpdfplumberが必要です。"
            "python3 -m pip install -r requirements-pdf.txt を実行してください。"
        )


def _bucket(value: int, size: int) -> int:
    """Quantize content counts so ordinary value changes do not look like layout drift."""
    return int(round(value / size) * size) if value else 0


def _page_structure(page: Any, page_number: int) -> dict[str, Any]:
    chars = len(page.chars or [])
    words = len(page.extract_words() or [])
    try:
        tables = len(page.find_tables() or [])
    except Exception:
        tables = 0
    return {
        "page": page_number,
        "width": round(float(page.width), 1),
        "height": round(float(page.height), 1),
        "character_count": chars,
        "word_count": words,
        "table_count": tables,
        "image_count": len(page.images or []),
    }


def inspect_pdf_layout(path: Path, *, minimum_text_characters: int = 20) -> dict[str, Any]:
    """Inspect page structure without returning source text or table values."""
    require_pdf_dependencies()
    path = Path(path)
    with pdfplumber.open(path) as pdf:
        pages = [_page_structure(page, number) for number, page in enumerate(pdf.pages, 1)]
    text_pages = sum(item["character_count"] >= minimum_text_characters for item in pages)
    low_text_pages = len(pages) - text_pages
    requires_ocr = bool(pages) and text_pages == 0
    structural_pages = [
        {
            "page": item["page"],
            "width": item["width"],
            "height": item["height"],
            "character_band": _bucket(item["character_count"], 100),
            "word_band": _bucket(item["word_count"], 25),
            "table_count": item["table_count"],
            "image_count": item["image_count"],
        }
        for item in pages
    ]
    encoded = json.dumps(structural_pages, sort_keys=True, separators=(",", ":")).encode()
    return {
        "page_count": len(pages),
        "text_pages": text_pages,
        "low_text_pages": low_text_pages,
        "requires_ocr": requires_ocr,
        "pages": pages,
        "fingerprint": hashlib.sha256(encoded).hexdigest(),
    }


def validate_pdf_layout(
    layout: dict[str, Any],
    *,
    min_pages: int = 1,
    max_pages: int | None = None,
    min_text_pages: int = 1,
    required_table_pages: Iterable[int] = (),
) -> dict[str, Any]:
    page_count = int(layout.get("page_count", 0))
    text_pages = int(layout.get("text_pages", 0))
    table_pages = {item["page"] for item in layout.get("pages", []) if item.get("table_count", 0) > 0}
    missing_table_pages = sorted(set(required_table_pages) - table_pages)
    reasons = []
    if page_count < min_pages:
        reasons.append("too_few_pages")
    if max_pages is not None and page_count > max_pages:
        reasons.append("too_many_pages")
    if text_pages < min_text_pages:
        reasons.append("insufficient_text_pages")
    if missing_table_pages:
        reasons.append("missing_required_tables")
    status = "ocr_required" if layout.get("requires_ocr") else "compatible" if not reasons else "incompatible"
    return {
        "status": status,
        "min_pages": min_pages,
        "max_pages": max_pages,
        "min_text_pages": min_text_pages,
        "required_table_pages": list(required_table_pages),
        "missing_table_pages": missing_table_pages,
        "reasons": reasons,
    }


def extract_page_text(path: Path, page_numbers: Iterable[int] | None = None) -> list[dict[str, Any]]:
    """Extract text in memory. Callers must keep returned content under private-data."""
    require_pdf_dependencies()
    wanted = set(page_numbers or [])
    records = []
    with pdfplumber.open(path) as pdf:
        for number, page in enumerate(pdf.pages, 1):
            if wanted and number not in wanted:
                continue
            records.append({
                "page": number,
                "width": float(page.width),
                "height": float(page.height),
                "text": page.extract_text() or "",
            })
    return records


def find_text(path: Path, needle: str, *, page_number: int | None = None) -> PdfTextMatch | None:
    """Locate the first literal text match and return a 1-based PDF page and bbox."""
    require_pdf_dependencies()
    if not needle:
        raise ValueError("needle must not be empty")
    with pdfplumber.open(path) as pdf:
        for number, page in enumerate(pdf.pages, 1):
            if page_number is not None and number != page_number:
                continue
            matches = page.search(re.escape(needle), regex=True, case=True) or []
            if matches:
                item = matches[0]
                return PdfTextMatch(
                    page=number,
                    text=str(item.get("text", needle)),
                    bbox=(float(item["x0"]), float(item["top"]), float(item["x1"]), float(item["bottom"])),
                )
    return None


def find_labeled_number(path: Path, label: str, *, page_number: int | None = None) -> tuple[float, PdfTextMatch] | None:
    """Find a number on the same extracted text line as a known label.

    This is intentionally conservative and is a building block for a
    REIT-specific parser, not a universal PDF table parser.
    """
    require_pdf_dependencies()
    with pdfplumber.open(path) as pdf:
        for number, page in enumerate(pdf.pages, 1):
            if page_number is not None and number != page_number:
                continue
            text = page.extract_text() or ""
            for line in text.splitlines():
                if label not in line:
                    continue
                tail = line.split(label, 1)[1]
                match = NUMBER_PATTERN.search(tail)
                if not match:
                    continue
                raw = match.group().replace(",", "")
                located = find_text(path, match.group(), page_number=number)
                if located:
                    return float(raw), located
    return None
