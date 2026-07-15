"""Privacy-safe workbook layout inspection and drift detection."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

CELL_REFERENCE = re.compile(r"^([A-Z]+)([0-9]+)$")


def _column_number(text: str) -> int:
    result = 0
    for char in text:
        result = result * 26 + ord(char) - 64
    return result


def inspect_workbook_layout(sheets: dict[str, dict[str, object]]) -> dict[str, Any]:
    """Return structure only; cell values never leave the parser."""
    sheet_reports = []
    for name in sorted(sheets):
        max_row = max_col = 0
        non_empty_cells = 0
        for reference, value in sheets[name].items():
            match = CELL_REFERENCE.match(reference)
            if not match:
                continue
            max_col = max(max_col, _column_number(match.group(1)))
            max_row = max(max_row, int(match.group(2)))
            if value not in (None, ""):
                non_empty_cells += 1
        sheet_reports.append({
            "name": name,
            "max_row": max_row,
            "max_column": max_col,
            "non_empty_cells": non_empty_cells,
        })
    structural = {"sheet_count": len(sheet_reports), "sheets": sheet_reports}
    encoded = json.dumps(structural, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return {**structural, "fingerprint": hashlib.sha256(encoded).hexdigest()}


def validate_workbook_layout(
    layout: dict[str, Any],
    *,
    required_sheets: tuple[str, ...] = (),
    required_name_fragments: tuple[str, ...] = (),
) -> dict[str, Any]:
    names = {sheet["name"] for sheet in layout["sheets"]}
    missing_sheets = [name for name in required_sheets if name not in names]
    missing_fragments = [fragment for fragment in required_name_fragments if not any(fragment in name for name in names)]
    return {
        "status": "compatible" if not missing_sheets and not missing_fragments else "incompatible",
        "required_sheets": list(required_sheets),
        "required_name_fragments": list(required_name_fragments),
        "missing_sheets": missing_sheets,
        "missing_name_fragments": missing_fragments,
    }
