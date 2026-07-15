#!/usr/bin/env python3
"""Download and parse NBF's current earnings PDF inside private-data only."""

from __future__ import annotations

import argparse
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from data_engine import ImportContext, LocalPdfAdapter, parse_nbf_earnings_presentation
from runtime_paths import (CACHE_DIR, NORMALIZED_DIR, PRIVATE_DATA_DIR,
                           QUARANTINE_DIR, RAW_DIR, REPORTS_DIR, ROOT,
                           ensure_private_dirs)

USER_AGENT = "J-REIT-Intelligence/0.10.1 local research prototype"


def download_pdf(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        content = response.read(30 * 1024 * 1024)
    if not content.startswith(b"%PDF-"):
        raise ValueError("downloaded source is not a PDF")
    return content


def main() -> int:
    parser = argparse.ArgumentParser(description="NBF公式決算説明会PDFをローカル専用データへ変換")
    parser.add_argument("--accept-source-terms", action="store_true")
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    if not args.accept_source_terms:
        print("中止: NBF公式サイトの利用上の注意を確認後、--accept-source-terms を付けてください。")
        return 2

    ensure_private_dirs()
    configs = json.loads((ROOT / "config/pdf-sources.json").read_text(encoding="utf-8"))
    config = configs["nbf_earnings_49"]
    target = RAW_DIR / config["local_filename"]
    if args.refresh or not target.is_file():
        target.write_bytes(download_pdf(config["download_url"]))

    context = ImportContext(
        root=ROOT, private_data_dir=PRIVATE_DATA_DIR, raw_dir=RAW_DIR,
        normalized_dir=NORMALIZED_DIR, cache_dir=CACHE_DIR,
        reports_dir=REPORTS_DIR, quarantine_dir=QUARANTINE_DIR,
        refresh=args.refresh,
    )
    adapter = LocalPdfAdapter(
        source_key="nbf_earnings_49", config=config,
        parser=parse_nbf_earnings_presentation, adapter_version="0.10.1",
    )
    result = adapter.run(context)
    report = {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "succeeded" if not result.issues else "review_required",
        "adapter_id": result.adapter_id,
        "adapter_version": result.adapter_version,
        "layout": result.layout_reports[0],
        "counts": result.report,
        "privacy": "原本文・物件名・抽出値はレポートへ保存していません。normalizedデータはprivate-data内限定です。",
    }
    # Avoid duplicating issue details because they may contain source labels.
    report["counts"] = {key: value for key, value in result.report.items() if key != "issues"}
    report["counts"]["issues"] = len(result.issues)
    report_dir = REPORTS_DIR / "pdf-imports"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "nbf-49-earnings-presentation.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "portfolio_metrics": result.report["portfolio_metrics"],
        "property_events": result.report["property_events"],
        "evidence_records": result.report["evidence_records"],
        "issues": len(result.issues),
        "private_output": str(NORMALIZED_DIR / config["output_filename"]),
        "private_report": str(report_path),
    }, ensure_ascii=False, indent=2))
    return 0 if not result.issues else 3


if __name__ == "__main__":
    raise SystemExit(main())
