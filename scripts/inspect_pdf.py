#!/usr/bin/env python3
"""Inspect a local private PDF without exporting its text or table values."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from data_engine import inspect_pdf_layout, validate_pdf_layout
from evidence import sha256_file
from runtime_paths import RAW_DIR, REPORTS_DIR, ensure_private_dirs


def private_pdf_path(filename: str) -> Path:
    relative = Path(filename)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("--file must be relative to private-data/raw")
    path = (RAW_DIR / relative).resolve()
    if not path.is_relative_to(RAW_DIR.resolve()):
        raise ValueError("PDF path escaped private-data/raw")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="private-data内PDFの構造を安全に検査します")
    parser.add_argument("--file", required=True, help="private-data/rawからの相対パス")
    parser.add_argument("--min-pages", type=int, default=1)
    parser.add_argument("--max-pages", type=int)
    parser.add_argument("--min-text-pages", type=int, default=1)
    args = parser.parse_args()
    ensure_private_dirs()
    path = private_pdf_path(args.file)
    if not path.is_file() or path.suffix.lower() != ".pdf":
        raise SystemExit(f"PDFが見つかりません: {path}")
    layout = inspect_pdf_layout(path)
    validation = validate_pdf_layout(
        layout,
        min_pages=args.min_pages,
        max_pages=args.max_pages,
        min_text_pages=args.min_text_pages,
    )
    report = {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {"local_filename": path.name, "sha256": sha256_file(path)},
        "layout": layout,
        "validation": validation,
        "privacy": "本文・表・物件名・数値はこのレポートへ保存していません。",
    }
    target_dir = REPORTS_DIR / "pdf-inspections"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{path.stem}-{layout['fingerprint'][:12]}.json"
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "status": validation["status"],
        "pages": layout["page_count"],
        "text_pages": layout["text_pages"],
        "requires_ocr": layout["requires_ocr"],
        "layout_fingerprint": layout["fingerprint"],
        "private_report": str(target),
    }, ensure_ascii=False, indent=2))
    return 0 if validation["status"] == "compatible" else 2


if __name__ == "__main__":
    raise SystemExit(main())
