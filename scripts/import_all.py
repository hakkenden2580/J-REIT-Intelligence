#!/usr/bin/env python3
"""NBF・JRE・GLPの公式Excelをローカル専用の横断データへ統合する。"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from data_engine import (AdapterRegistry, ImportContext, NbfWorkbookSetAdapter,
                         SingleWorkbookExcelAdapter, evaluate_dataset,
                         execute_import_run)
from evidence import metric_evidence, source_document
from import_nbf import (canonical_name, cell, col_name, geocode, million_yen,
                        number_or_none, percent_from_fraction, read_xlsx, request_bytes)
from runtime_paths import (CACHE_DIR, NORMALIZED_DIR, PRIVATE_DATA_DIR,
                           QUARANTINE_DIR, RAW_DIR, REPORTS_DIR, ROOT,
                           ensure_private_dirs)


def numeric_text(value):
    if isinstance(value, (int, float)):
        return value
    text = str(value or "").strip().replace(",", "").replace(" ", "")
    if not text or text in {"-", "－", "—", "非開示（注1）"}:
        return None
    negative = text.startswith(("△", "▲", "-"))
    match = re.search(r"\d+(?:\.\d+)?", text)
    if not match:
        return None
    number = float(match.group())
    return -number if negative else number


def region_from_address(address: str) -> str:
    if address.startswith("東京都"):
        return "東京都"
    if address.startswith(("神奈川県", "千葉県", "埼玉県", "茨城県", "栃木県", "群馬県")):
        return "首都圏"
    if address.startswith(("大阪府", "京都府", "兵庫県", "滋賀県", "奈良県", "和歌山県")):
        return "関西圏"
    if address.startswith(("愛知県", "岐阜県", "三重県", "静岡県")):
        return "中部圏"
    return "その他"


def stable_id(prefix: str, name: str) -> str:
    digest = hashlib.sha1(canonical_name(name).encode("utf-8")).hexdigest()[:10].upper()
    return f"{prefix}-{digest}"


def jre_period_date(period_no: int) -> str:
    year = 2001 + (period_no + 1) // 2
    month, day = (3, 31) if period_no % 2 else (9, 30)
    return f"{year:04d}-{month:02d}-{day:02d}"


def parse_jre(path: Path, config: dict, cache: dict) -> tuple[dict, dict]:
    sheets = read_xlsx(path)
    required = ["基礎データ", "期末賃貸可能面積", "期末賃貸面積", "期末入居率", "期末テナント数",
                "期末簿価", "鑑定機関による期末算定価格", "ＮＯＩ"]
    missing = [name for name in required if name not in sheets]
    if missing:
        raise ValueError(f"JREシート不足: {missing}")
    base = sheets["基礎データ"]
    metric_sheets = {"leasable_area": sheets["期末賃貸可能面積"], "leased_area": sheets["期末賃貸面積"],
                     "occupancy": sheets["期末入居率"], "tenants": sheets["期末テナント数"],
                     "book_value": sheets["期末簿価"], "appraisal": sheets["鑑定機関による期末算定価格"],
                     "noi": sheets["ＮＯＩ"]}
    period_cols = [(cell(metric_sheets["book_value"], col, 4), col) for col in range(3, 100)
                   if isinstance(cell(metric_sheets["book_value"], col, 4), int)]
    period_cols = sorted(period_cols)[-10:]
    latest_no, latest_col = max(period_cols)
    source_base = source_document(
        path,
        publisher=config["reit_name"],
        title="保有物件データ",
        period=config["period"],
        as_of_date=config["as_of_date"],
        url=config["library_url"],
        download_url=config["download_url"],
    )
    properties, issues = [], []
    for row in range(6, 160):
        name, address = cell(base, 2, row), cell(base, 3, row)
        latest_book = number_or_none(cell(metric_sheets["book_value"], latest_col, row))
        if not name or not address or latest_book is None:
            continue
        name, address = str(name).strip(), str(address).strip()
        geo = geocode(address, cache)
        history = []
        for period_no, col in period_cols:
            period_label = f"第{period_no}期"
            period_date = jre_period_date(period_no)
            source_cells = {key: f"{sheet}!{col_name(col)}{row}" for key, sheet in {
                "leasable_area":"期末賃貸可能面積", "leased_area":"期末賃貸面積", "occupancy":"期末入居率",
                "tenants":"期末テナント数", "book_value":"期末簿価", "appraisal":"鑑定機関による期末算定価格",
                "noi":"ＮＯＩ"}.items()}
            if period_no == latest_no:
                source_cells["price"] = f"基礎データ!L{row}"
            values = {
                "period_no": period_no, "period": period_label, "as_of_date": period_date,
                "price": million_yen(cell(base, 12, row)) if period_no == latest_no else None,
                "leasable_area": number_or_none(cell(metric_sheets["leasable_area"], col, row)),
                "leased_area": number_or_none(cell(metric_sheets["leased_area"], col, row)),
                "occupancy": percent_from_fraction(cell(metric_sheets["occupancy"], col, row)),
                "tenants": number_or_none(cell(metric_sheets["tenants"], col, row)),
                "book_value": number_or_none(cell(metric_sheets["book_value"], col, row)),
                "appraisal": number_or_none(cell(metric_sheets["appraisal"], col, row)),
                "noi": (numeric_text(cell(metric_sheets["noi"], col, row)) or 0) / 1000 if numeric_text(cell(metric_sheets["noi"], col, row)) is not None else None,
                "cap": None, "discount_rate": None, "terminal_cap_rate": None,
            }
            source = {**source_base, "period": period_label, "as_of_date": period_date, "cells": source_cells}
            values["source"] = source
            values["evidence"] = metric_evidence(values, source, source_cells, parser_name="jre_excel")
            if any(values[key] is not None for key in ("occupancy", "book_value", "appraisal", "noi")):
                history.append(values)
        if not history:
            issues.append({"property": name, "message": "履歴なし"}); continue
        current = history[-1]
        current_source = current["source"]
        current_source["cells"].update({"address": f"基礎データ!C{row}"})
        properties.append({"id": stable_id("JRE", name), "name": name, "reit": config["reit_name"], "reit_code": config["reit_code"],
                           "type": "オフィス", "region": region_from_address(address), "address": address,
                           "lat": geo["lat"], "lng": geo["lng"], "geocode": geo,
                           "price": million_yen(cell(base, 12, row)), "book_value": current["book_value"],
                           "appraisal": current["appraisal"], "leasable_area": current["leasable_area"],
                           "leased_area": current["leased_area"], "tenants": current["tenants"], "occupancy": current["occupancy"],
                           "cap": None, "discount_rate": None, "terminal_cap_rate": None, "noi": current["noi"],
                           "source": current_source, "evidence": current["evidence"], "periods": history})
    payload = {"meta": {"dataset": "jre-official-local", "label": f"JRE 第{latest_no}期・過去{len(period_cols)}期",
                        "reit_code": config["reit_code"], "as_of_date": config["as_of_date"], "periods": len(period_cols),
                        "source_url": config["library_url"], "notice": "利用者のMac内で変換したローカル分析用データ。"},
               "properties": properties}
    report = {"properties": len(properties), "periods": len(period_cols), "history_points": sum(len(p["periods"]) for p in properties),
              "with_coordinates": sum(p["lat"] is not None for p in properties), "with_noi": sum(p["noi"] is not None for p in properties),
              "with_cap": 0, "issues": issues}
    return payload, report


def parse_glp(path: Path, config: dict, cache: dict) -> tuple[dict, dict]:
    sheets = read_xlsx(path)
    portfolio, appraisal, income = sheets["ポートフォリオ一覧"], sheets["鑑定評価額一覧"], sheets["賃貸借の概況及び損益状況"]
    appraisal_rows = {str(cell(appraisal, 1, row)).strip(): row for row in range(7, 180) if cell(appraisal, 1, row)}
    income_cols = {str(cell(income, col, 5)).strip(): col for col in range(5, 160) if cell(income, col, 5)}
    source_base = source_document(
        path,
        publisher=config["reit_name"],
        title="第28期 物件データ",
        period="第28期",
        as_of_date="2026-02-28",
        url=config["library_url"],
        download_url=config["download_url"],
    )
    properties, issues = [], []
    for row in range(6, 180):
        property_no, name, address = cell(portfolio, 1, row), cell(portfolio, 2, row), cell(portfolio, 3, row)
        if not property_no or not name or not address or not re.search(r"(?:圏|その他)-", str(property_no)):
            continue
        property_no, name, address = str(property_no).strip(), str(name).strip(), str(address).strip()
        appraisal_row, income_col = appraisal_rows.get(property_no), income_cols.get(property_no)
        if appraisal_row is None:
            issues.append({"property": name, "field": "appraisal", "message": "鑑定シートを照合できません"})
        if income_col is None:
            issues.append({"property": name, "field": "noi", "message": "収益シートを照合できません"})
        geo = geocode(address, cache)
        current_cap = percent_from_fraction(cell(appraisal, 6, appraisal_row)) if appraisal_row else None
        current_discount = percent_from_fraction(cell(appraisal, 9, appraisal_row)) if appraisal_row else None
        current_terminal = percent_from_fraction(cell(appraisal, 10, appraisal_row)) if appraisal_row else None
        # GLP workbook contains explicit zeroes where yield metrics are not applicable.
        # A 0% cap rate must not be presented as a real valuation observation.
        current_cap = None if current_cap == 0 else current_cap
        current_discount = None if current_discount == 0 else current_discount
        current_terminal = None if current_terminal == 0 else current_terminal
        previous_cap = percent_from_fraction(cell(appraisal, 14, appraisal_row)) if appraisal_row else None
        previous_cap = None if previous_cap == 0 else previous_cap
        current_cells = {
            "address": f"ポートフォリオ一覧!C{row}", "price": f"ポートフォリオ一覧!E{row}",
            "leasable_area": f"ポートフォリオ一覧!G{row}", "leased_area": f"ポートフォリオ一覧!H{row}",
            "occupancy": f"ポートフォリオ一覧!I{row}", "tenants": f"ポートフォリオ一覧!J{row}",
            "appraisal": f"鑑定評価額一覧!C{appraisal_row}" if appraisal_row else None,
            "cap": f"鑑定評価額一覧!F{appraisal_row}" if appraisal_row else None,
            "discount_rate": f"鑑定評価額一覧!I{appraisal_row}" if appraisal_row else None,
            "terminal_cap_rate": f"鑑定評価額一覧!J{appraisal_row}" if appraisal_row else None,
            "book_value": f"鑑定評価額一覧!K{appraisal_row}" if appraisal_row else None,
            "noi": f"賃貸借の概況及び損益状況!{col_name(income_col)}16" if income_col else None,
        }
        current_source = {**source_base, "cells": current_cells}
        current = {
            "period_no": 28, "period": "第28期", "as_of_date": "2026-02-28", "price": number_or_none(cell(portfolio, 5, row)),
            "book_value": number_or_none(cell(appraisal, 11, appraisal_row)) if appraisal_row else None,
            "appraisal": number_or_none(cell(appraisal, 3, appraisal_row)) if appraisal_row else None,
            "leasable_area": number_or_none(cell(portfolio, 7, row)), "leased_area": number_or_none(cell(portfolio, 8, row)),
            "occupancy": number_or_none(cell(portfolio, 9, row)), "tenants": number_or_none(cell(portfolio, 10, row)),
            "cap": current_cap, "discount_rate": current_discount,
            "terminal_cap_rate": current_terminal,
            "noi": (numeric_text(cell(income, income_col, 16)) / 1000) if income_col and numeric_text(cell(income, income_col, 16)) is not None else None,
            "source": current_source,
        }
        current["evidence"] = metric_evidence(current, current_source, current_cells, parser_name="glp_excel")
        previous_cells = {
            "appraisal": f"鑑定評価額一覧!M{appraisal_row}" if appraisal_row else None,
            "cap": f"鑑定評価額一覧!N{appraisal_row}" if appraisal_row else None,
        }
        previous_source = {**source_base, "document": "第28期 物件データ（前期比較欄）", "title": "第28期 物件データ（前期比較欄）",
                           "period": "第27期", "as_of_date": "2025-08-31", "cells": previous_cells}
        previous = {"period_no": 27, "period": "第27期", "as_of_date": "2025-08-31", "price": None, "book_value": None,
                    "appraisal": number_or_none(cell(appraisal, 13, appraisal_row)) if appraisal_row else None,
                    "leasable_area": None, "leased_area": None, "occupancy": None, "tenants": None, "cap": previous_cap,
                    "discount_rate": None, "terminal_cap_rate": None, "noi": None, "source": previous_source}
        previous["evidence"] = metric_evidence(previous, previous_source, previous_cells, parser_name="glp_excel")
        region = "関東圏" if property_no.startswith("関東圏") else "関西圏" if property_no.startswith("関西圏") else "その他"
        properties.append({"id": stable_id("GLP", name), "name": name, "reit": config["reit_name"], "reit_code": config["reit_code"],
                           "type": "物流", "region": region, "address": address, "lat": geo["lat"], "lng": geo["lng"], "geocode": geo,
                           **{key: current[key] for key in ("price","book_value","appraisal","leasable_area","leased_area","occupancy","tenants","cap","discount_rate","terminal_cap_rate","noi")},
                           "source": current["source"], "evidence": current["evidence"], "periods": [previous, current]})
    payload = {"meta": {"dataset": "glp-official-local", "label": "GLP 第28期", "reit_code": config["reit_code"],
                        "as_of_date": config["as_of_date"], "periods": 2, "source_url": config["library_url"],
                        "notice": "利用者のMac内で変換したローカル分析用データ。公開・再配布しないでください。"},
               "properties": properties}
    report = {"properties": len(properties), "periods": 2, "history_points": sum(len(p["periods"]) for p in properties),
              "with_coordinates": sum(p["lat"] is not None for p in properties), "with_noi": sum(p["noi"] is not None for p in properties),
              "with_cap": sum(p["cap"] is not None for p in properties), "issues": issues}
    return payload, report


def cli_summary(report: dict) -> dict:
    run = report["import_run"]
    layout_values = set(run.get("layout_statuses", {}).values())
    layout = "changed" if "changed" in layout_values else "unchanged" if layout_values == {"unchanged"} else "new"
    return {
        "status": "succeeded" if report["quality"]["status"] != "failed" else "failed",
        "properties": report["properties"],
        "by_reit": report["by_reit"],
        "import_run_id": run["run_id"],
        "same_inputs": bool(run.get("same_inputs_as_run_id")),
        "layout_status": layout,
        "quality": report["quality"],
        "adapter_issues": len(report["issues"]),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--accept-source-terms", action="store_true")
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--verbose", action="store_true", help="詳細なAdapter監査情報をターミナルへ表示")
    args = parser.parse_args()
    if not args.accept_source_terms:
        print("中止: 各公式ファイルの利用上の注意を確認後、--accept-source-terms を付けてください。", file=sys.stderr)
        return 2
    ensure_private_dirs()
    configs = json.loads((ROOT / "config/sources.json").read_text(encoding="utf-8"))
    cache_path = CACHE_DIR / "geocode-cache.json"
    cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
    context = ImportContext(
        root=ROOT,
        private_data_dir=PRIVATE_DATA_DIR,
        raw_dir=RAW_DIR,
        normalized_dir=NORMALIZED_DIR,
        cache_dir=CACHE_DIR,
        reports_dir=REPORTS_DIR,
        quarantine_dir=QUARANTINE_DIR,
        refresh=args.refresh,
        shared_state={"geocode_cache": cache},
    )
    registry = AdapterRegistry()
    registry.register(NbfWorkbookSetAdapter(
        config=configs["nbf"], request_bytes=request_bytes, read_xlsx=read_xlsx
    ))
    registry.register(SingleWorkbookExcelAdapter(
        source_key="jre", config=configs["jre"], parser=parse_jre,
        request_bytes=request_bytes, read_xlsx=read_xlsx,
        required_sheets=("基礎データ", "期末賃貸可能面積", "期末賃貸面積", "期末入居率",
                         "期末テナント数", "期末簿価", "鑑定機関による期末算定価格", "ＮＯＩ"),
        title="保有物件データ",
    ))
    registry.register(SingleWorkbookExcelAdapter(
        source_key="glp", config=configs["glp"], parser=parse_glp,
        request_bytes=request_bytes, read_xlsx=read_xlsx,
        required_sheets=("ポートフォリオ一覧", "鑑定評価額一覧", "賃貸借の概況及び損益状況"),
        title="物件データ", adapter_version="0.7.0",
    ))
    results, import_run = execute_import_run(registry.select(["nbf", "jre", "glp"]), context)
    cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    nbf = results["nbf"].payload
    jre = results["jre"].payload
    glp = results["glp"].payload
    combined = nbf["properties"] + jre["properties"] + glp["properties"]
    payload = {"meta": {"dataset": "multi-reit-official-local", "label": "NBF・JRE・GLP 横断データ",
                        "reit_codes": ["8951","8952","3281"], "as_of_date": max(nbf["meta"]["as_of_date"],jre["meta"]["as_of_date"],glp["meta"]["as_of_date"]),
                        "generated_at": datetime.now(timezone.utc).isoformat(),
                        "data_engine_version": "0.7.0", "import_run_id": import_run["run_id"],
                        "notice": "各社公式ファイルを利用者のMac内で変換したローカル分析用データ。公開・再配布しないでください。"},
               "properties": combined}
    quality_report = evaluate_dataset(payload, import_run_id=import_run["run_id"])
    payload["meta"]["data_quality"] = {
        "status": quality_report["status"],
        "evidence_coverage_percent": quality_report["totals"]["evidence_coverage_percent"],
        "coordinate_coverage_percent": quality_report["totals"]["coordinate_coverage_percent"],
    }
    all_report = {"properties": len(combined), "by_reit": {"NBF": len(nbf["properties"]), "JRE": len(jre["properties"]), "GLP": len(glp["properties"])},
                  "import_run": import_run,
                  "quality": {"status": quality_report["status"], "totals": quality_report["totals"]},
                  "nbf": results["nbf"].report, "jre": results["jre"].report, "glp": results["glp"].report,
                  "issues": results["nbf"].issues + results["jre"].issues + results["glp"].issues}
    quality_name = f"quality-{import_run['run_id']}.json"
    (REPORTS_DIR / quality_name).write_text(json.dumps(quality_report, ensure_ascii=False, indent=2), encoding="utf-8")
    (REPORTS_DIR / "latest-quality-report.json").write_text(json.dumps(quality_report, ensure_ascii=False, indent=2), encoding="utf-8")
    (REPORTS_DIR / "all-import-report.json").write_text(json.dumps(all_report, ensure_ascii=False, indent=2), encoding="utf-8")
    if quality_report["status"] == "failed":
        quarantine = {"run_id": import_run["run_id"], "reason": "data_quality_failed", "totals": quality_report["totals"]}
        (QUARANTINE_DIR / f"quality-{import_run['run_id']}.json").write_text(
            json.dumps(quarantine, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(json.dumps(all_report if args.verbose else cli_summary(all_report), ensure_ascii=False, indent=2))
        print("中止: データ品質Gateでエラーを検出したため、既存の正常データは上書きしません。", file=sys.stderr)
        return 1
    (NORMALIZED_DIR / "properties.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(all_report if args.verbose else cli_summary(all_report), ensure_ascii=False, indent=2))
    expected = all(result.payload.get("properties") for result in results.values()) and not all_report["issues"]
    return 0 if expected else 1


if __name__ == "__main__":
    raise SystemExit(main())
