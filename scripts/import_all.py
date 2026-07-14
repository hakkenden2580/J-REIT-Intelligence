#!/usr/bin/env python3
"""NBF・JRE・GLPの公式Excelをローカル専用の横断データへ統合する。"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from import_nbf import (ROOT, canonical_name, cell, col_name, geocode, million_yen,
                        number_or_none, percent_from_fraction, read_xlsx, request_bytes)


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
            values = {
                "period_no": period_no, "period": f"第{period_no}期", "as_of_date": jre_period_date(period_no),
                "price": million_yen(cell(base, 12, row)) if period_no == latest_no else None,
                "leasable_area": number_or_none(cell(metric_sheets["leasable_area"], col, row)),
                "leased_area": number_or_none(cell(metric_sheets["leased_area"], col, row)),
                "occupancy": percent_from_fraction(cell(metric_sheets["occupancy"], col, row)),
                "tenants": number_or_none(cell(metric_sheets["tenants"], col, row)),
                "book_value": number_or_none(cell(metric_sheets["book_value"], col, row)),
                "appraisal": number_or_none(cell(metric_sheets["appraisal"], col, row)),
                "noi": (numeric_text(cell(metric_sheets["noi"], col, row)) or 0) / 1000 if numeric_text(cell(metric_sheets["noi"], col, row)) is not None else None,
                "cap": None, "discount_rate": None, "terminal_cap_rate": None,
                "source": {"document": "保有物件データ", "period": f"第{period_no}期", "as_of_date": jre_period_date(period_no),
                           "url": config["library_url"], "download_url": config["download_url"],
                           "cells": {key: f"{sheet}!{col_name(col)}{row}" for key, sheet in {
                               "leasable_area":"期末賃貸可能面積","leased_area":"期末賃貸面積","occupancy":"期末入居率",
                               "tenants":"期末テナント数","book_value":"期末簿価","appraisal":"鑑定機関による期末算定価格","noi":"ＮＯＩ"}.items()}}
            }
            if any(values[key] is not None for key in ("occupancy", "book_value", "appraisal", "noi")):
                history.append(values)
        if not history:
            issues.append({"property": name, "message": "履歴なし"}); continue
        current = history[-1]
        current_source = current["source"]
        current_source["cells"].update({"address": f"基礎データ!C{row}", "price": f"基礎データ!L{row}"})
        properties.append({"id": stable_id("JRE", name), "name": name, "reit": config["reit_name"], "reit_code": config["reit_code"],
                           "type": "オフィス", "region": region_from_address(address), "address": address,
                           "lat": geo["lat"], "lng": geo["lng"], "geocode": geo,
                           "price": million_yen(cell(base, 12, row)), "book_value": current["book_value"],
                           "appraisal": current["appraisal"], "leasable_area": current["leasable_area"],
                           "leased_area": current["leased_area"], "tenants": current["tenants"], "occupancy": current["occupancy"],
                           "cap": None, "discount_rate": None, "terminal_cap_rate": None, "noi": current["noi"],
                           "source": current_source, "periods": history})
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
        previous_cap = percent_from_fraction(cell(appraisal, 14, appraisal_row)) if appraisal_row else None
        current = {
            "period_no": 28, "period": "第28期", "as_of_date": "2026-02-28", "price": number_or_none(cell(portfolio, 5, row)),
            "book_value": number_or_none(cell(appraisal, 11, appraisal_row)) if appraisal_row else None,
            "appraisal": number_or_none(cell(appraisal, 3, appraisal_row)) if appraisal_row else None,
            "leasable_area": number_or_none(cell(portfolio, 7, row)), "leased_area": number_or_none(cell(portfolio, 8, row)),
            "occupancy": number_or_none(cell(portfolio, 9, row)), "tenants": number_or_none(cell(portfolio, 10, row)),
            "cap": current_cap, "discount_rate": percent_from_fraction(cell(appraisal, 9, appraisal_row)) if appraisal_row else None,
            "terminal_cap_rate": percent_from_fraction(cell(appraisal, 10, appraisal_row)) if appraisal_row else None,
            "noi": (numeric_text(cell(income, income_col, 16)) / 1000) if income_col and numeric_text(cell(income, income_col, 16)) is not None else None,
            "source": {"document": "第28期 物件データ", "period": "第28期", "as_of_date": "2026-02-28",
                       "url": config["library_url"], "download_url": config["download_url"],
                       "cells": {"address": f"ポートフォリオ一覧!C{row}", "price": f"ポートフォリオ一覧!E{row}",
                                 "leasable_area": f"ポートフォリオ一覧!G{row}", "leased_area": f"ポートフォリオ一覧!H{row}",
                                 "occupancy": f"ポートフォリオ一覧!I{row}", "tenants": f"ポートフォリオ一覧!J{row}",
                                 "appraisal": f"鑑定評価額一覧!C{appraisal_row}" if appraisal_row else None,
                                 "cap": f"鑑定評価額一覧!F{appraisal_row}" if appraisal_row else None,
                                 "book_value": f"鑑定評価額一覧!K{appraisal_row}" if appraisal_row else None,
                                 "noi": f"賃貸借の概況及び損益状況!{col_name(income_col)}16" if income_col else None}}
        }
        previous = {"period_no": 27, "period": "第27期", "as_of_date": "2025-08-31", "price": None, "book_value": None,
                    "appraisal": number_or_none(cell(appraisal, 13, appraisal_row)) if appraisal_row else None,
                    "leasable_area": None, "leased_area": None, "occupancy": None, "tenants": None, "cap": previous_cap,
                    "discount_rate": None, "terminal_cap_rate": None, "noi": None,
                    "source": {"document": "第28期 物件データ（前期比較欄）", "period": "第27期", "as_of_date": "2025-08-31",
                               "url": config["library_url"], "download_url": config["download_url"],
                               "cells": {"appraisal": f"鑑定評価額一覧!M{appraisal_row}" if appraisal_row else None,
                                         "cap": f"鑑定評価額一覧!N{appraisal_row}" if appraisal_row else None}}}
        region = "関東圏" if property_no.startswith("関東圏") else "関西圏" if property_no.startswith("関西圏") else "その他"
        properties.append({"id": stable_id("GLP", name), "name": name, "reit": config["reit_name"], "reit_code": config["reit_code"],
                           "type": "物流", "region": region, "address": address, "lat": geo["lat"], "lng": geo["lng"], "geocode": geo,
                           **{key: current[key] for key in ("price","book_value","appraisal","leasable_area","leased_area","occupancy","tenants","cap","discount_rate","terminal_cap_rate","noi")},
                           "source": current["source"], "periods": [previous, current]})
    payload = {"meta": {"dataset": "glp-official-local", "label": "GLP 第28期", "reit_code": config["reit_code"],
                        "as_of_date": config["as_of_date"], "periods": 2, "source_url": config["library_url"],
                        "notice": "利用者のMac内で変換したローカル分析用データ。公開・再配布しないでください。"},
               "properties": properties}
    report = {"properties": len(properties), "periods": 2, "history_points": sum(len(p["periods"]) for p in properties),
              "with_coordinates": sum(p["lat"] is not None for p in properties), "with_noi": sum(p["noi"] is not None for p in properties),
              "with_cap": sum(p["cap"] is not None for p in properties), "issues": issues}
    return payload, report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--accept-source-terms", action="store_true")
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    if not args.accept_source_terms:
        print("中止: 各公式ファイルの利用上の注意を確認後、--accept-source-terms を付けてください。", file=sys.stderr)
        return 2
    nbf_command = [sys.executable, str(ROOT / "scripts/import_nbf.py"), "--accept-source-terms"]
    if args.refresh: nbf_command.append("--refresh")
    subprocess.run(nbf_command, cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
    configs = json.loads((ROOT / "config/sources.json").read_text(encoding="utf-8"))
    raw_dir, data_dir = ROOT / "sources/raw", ROOT / "data"
    cache_path = data_dir / "geocode-cache.json"
    cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
    results, reports = {}, {}
    for key, parser_fn in (("jre", parse_jre), ("glp", parse_glp)):
        config = configs[key]; path = raw_dir / config["local_filename"]
        if args.refresh or not path.exists():
            print(f"download: {config['reit_name']} {config['period']}", file=sys.stderr)
            path.write_bytes(request_bytes(config["download_url"]))
        payload, report = parser_fn(path, config, cache)
        results[key], reports[key] = payload, report
        (data_dir / f"{key}-properties.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    nbf = json.loads((data_dir / "nbf-properties.json").read_text(encoding="utf-8"))
    combined = nbf["properties"] + results["jre"]["properties"] + results["glp"]["properties"]
    payload = {"meta": {"dataset": "multi-reit-official-local", "label": "NBF・JRE・GLP 横断データ",
                        "reit_codes": ["8951","8952","3281"], "as_of_date": max(nbf["meta"]["as_of_date"],results["jre"]["meta"]["as_of_date"],results["glp"]["meta"]["as_of_date"]),
                        "generated_at": datetime.now(timezone.utc).isoformat(),
                        "notice": "各社公式ファイルを利用者のMac内で変換したローカル分析用データ。公開・再配布しないでください。"},
               "properties": combined}
    all_report = {"properties": len(combined), "by_reit": {"NBF": len(nbf["properties"]), "JRE": len(results["jre"]["properties"]), "GLP": len(results["glp"]["properties"])},
                  "jre": reports["jre"], "glp": reports["glp"], "issues": reports["jre"]["issues"] + reports["glp"]["issues"]}
    (data_dir / "properties.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (data_dir / "all-import-report.json").write_text(json.dumps(all_report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(all_report, ensure_ascii=False, indent=2))
    expected = len(combined) == 234 and not all_report["issues"]
    return 0 if expected else 1


if __name__ == "__main__":
    raise SystemExit(main())
