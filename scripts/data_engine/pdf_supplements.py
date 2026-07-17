"""Discover normalized PDF supplements without serving private paths."""

from __future__ import annotations

import json
from pathlib import Path

SUPPLEMENT_PATTERNS = ("*-earnings-presentation.json", "*-pdf-supplement.json")


def discover_supplement_paths(normalized_dir: Path) -> list[Path]:
    paths: set[Path] = set()
    for pattern in SUPPLEMENT_PATTERNS:
        paths.update(normalized_dir.glob(pattern))
    return sorted(path for path in paths if path.is_file())


def load_pdf_supplements(normalized_dir: Path) -> list[dict]:
    records = []
    for path in discover_supplement_paths(normalized_dir):
        record = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(record, dict):
            raise ValueError(f"PDF supplement is not an object: {path.name}")
        if "meta" not in record or not any(key in record for key in ("portfolio_metrics", "property_events")):
            raise ValueError(f"PDF supplement has no supported records: {path.name}")
        records.append(record)
    return records
