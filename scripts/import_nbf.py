#!/usr/bin/env python3
"""NBF公式「物件毎データ」10期分をローカル分析用JSONへ変換する。

外部Pythonパッケージを使わず、xlsx (ZIP/XML) を直接読み取る。
原本と生成データは.gitignore対象で、公開リポジトリへ含めない。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

from evidence import metric_evidence, source_document
from runtime_paths import CACHE_DIR, NORMALIZED_DIR, RAW_DIR, REPORTS_DIR, ROOT, ensure_private_dirs

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
REL_NS = {"r": "http://schemas.openxmlformats.org/package/2006/relationships"}
DOC_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
GSI_URL = "https://msearch.gsi.go.jp/address-search/AddressSearch"
USER_AGENT = "J-REIT-Intelligence/0.6 local research prototype"


def request_bytes(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=45) as res:
        return res.read()


def shared_strings(archive: zipfile.ZipFile) -> list[str]:
    try:
        root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    except KeyError:
        return []
    return ["".join(t.text or "" for t in si.findall(".//m:t", NS)) for si in root.findall("m:si", NS)]


def sheet_paths(archive: zipfile.ZipFile) -> dict[str, str]:
    workbook = ET.fromstring(archive.read("xl/workbook.xml"))
    rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    rel_map = {rel.attrib["Id"]: rel.attrib["Target"] for rel in rels.findall("r:Relationship", REL_NS)}
    result = {}
    for sheet in workbook.findall("m:sheets/m:sheet", NS):
        rel_id = sheet.attrib[f"{{{DOC_REL}}}id"]
        target = rel_map[rel_id].lstrip("/")
        result[sheet.attrib["name"]] = target if target.startswith("xl/") else f"xl/{target}"
    return result


def parse_value(cell_element: ET.Element, strings: list[str]):
    kind = cell_element.attrib.get("t")
    value = cell_element.find("m:v", NS)
    if kind == "inlineStr":
        return "".join(t.text or "" for t in cell_element.findall(".//m:t", NS))
    if value is None:
        return None
    raw = value.text or ""
    if kind == "s":
        return strings[int(raw)]
    if kind in {"str", "e"}:
        return raw
    if kind == "b":
        return raw == "1"
    try:
        number = float(raw)
        return int(number) if number.is_integer() else number
    except ValueError:
        return raw


def read_xlsx(path: Path) -> dict[str, dict[str, object]]:
    with zipfile.ZipFile(path) as archive:
        strings = shared_strings(archive)
        sheets = {}
        for name, xml_path in sheet_paths(archive).items():
            root = ET.fromstring(archive.read(xml_path))
            cells = {}
            for element in root.findall(".//m:sheetData/m:row/m:c", NS):
                cells[element.attrib["r"]] = parse_value(element, strings)
            sheets[name] = cells
        return sheets


def col_name(number: int) -> str:
    text = ""
    while number:
        number, rem = divmod(number - 1, 26)
        text = chr(65 + rem) + text
    return text


def cell(cells: dict[str, object], col: int, row: int):
    return cells.get(f"{col_name(col)}{row}")


def clean_name(value: object) -> str:
    return re.sub(r"\s*\*\d+\s*$", "", str(value or "")).replace("\u3000", " ").strip()


def canonical_name(value: object) -> str:
    normalized = unicodedata.normalize("NFKC", clean_name(value)).lower()
    return re.sub(r"[\s・･]", "", normalized)


def number_or_none(value):
    return value if isinstance(value, (int, float)) else None


def million_yen(value):
    value = number_or_none(value)
    return round(value / 1_000_000, 3) if value is not None else None


def percent_from_fraction(value):
    value = number_or_none(value)
    return round(value * 100, 3) if value is not None else None


def find_row(cells: dict[str, object], predicate, max_row: int = 200) -> int | None:
    for row in range(1, max_row + 1):
        if predicate(row):
            return row
    return None


def geocode(address: str, cache: dict[str, object]):
    if address in cache:
        return cache[address]
    url = GSI_URL + "?" + urllib.parse.urlencode({"q": address})
    try:
        results = json.loads(request_bytes(url).decode("utf-8"))
        if results:
            lon, lat = results[0]["geometry"]["coordinates"]
            result = {"lat": lat, "lng": lon, "matched_address": results[0].get("properties", {}).get("title"),
                      "quality": "automatic", "provider": "GSI AddressSearch"}
        else:
            result = {"lat": None, "lng": None, "matched_address": None, "quality": "unknown", "provider": "GSI AddressSearch"}
    except Exception as exc:
        result = {"lat": None, "lng": None, "matched_address": None, "quality": "error",
                  "provider": "GSI AddressSearch", "error": str(exc)}
    cache[address] = result
    time.sleep(0.15)
    return result


def source_reconciliation(portfolio: dict[str, object], total_row: int, snapshots: list[dict]) -> dict:
    source_totals = {
        "price": million_yen(cell(portfolio, 4, total_row)), "book_value": million_yen(cell(portfolio, 5, total_row)),
        "appraisal": million_yen(cell(portfolio, 6, total_row)), "leasable_area": number_or_none(cell(portfolio, 7, total_row)),
        "leased_area": number_or_none(cell(portfolio, 8, total_row)), "tenants": number_or_none(cell(portfolio, 9, total_row))
    }
    normalized = {key: round(sum((item.get(key) or 0) for item in snapshots), 3) for key in source_totals}
    tolerances = {"price": 0.02, "book_value": 0.02, "appraisal": 0.02,
                  "leasable_area": 5, "leased_area": 5, "tenants": 0}
    result = {}
    for key, source_value in source_totals.items():
        difference = round(normalized[key] - source_value, 3) if source_value is not None else None
        result[key] = {"source": source_value, "normalized": normalized[key], "difference": difference,
                       "tolerance": tolerances[key],
                       "status": "ok" if difference is not None and abs(difference) <= tolerances[key] else "review"}
    return result


def parse_period(source_path: Path, period: dict, common: dict) -> tuple[list[dict], dict, list[dict]]:
    sheets = read_xlsx(source_path)
    portfolio_name = next((name for name in sheets if name == "データシート"), None)
    income_name = next((name for name in sheets if "収益" in name), None)
    if not portfolio_name or not income_name:
        raise ValueError(f"{period['period']}: 必要なシートが見つかりません: {list(sheets)}")
    portfolio, income = sheets[portfolio_name], sheets[income_name]
    header_row = find_row(portfolio, lambda row: str(cell(portfolio, 2, row) or "").strip() in {"物件名称", "物件名"}, 30)
    total_row = find_row(portfolio, lambda row: "全物件" in str(cell(portfolio, 2, row) or ""), 40)
    income_header = find_row(income, lambda row: str(cell(income, 1, row) or "").strip() == "科目", 30)
    noi_row = find_row(income, lambda row: "NOI" in str(cell(income, 1, row) or "") or "NOI" in str(cell(income, 2, row) or ""), 50)
    if None in {header_row, total_row, income_header, noi_row}:
        raise ValueError(f"{period['period']}: ヘッダーまたはNOI行を検出できません")
    income_columns = {}
    for col in range(1, 220):
        value = cell(income, col, income_header)
        if value:
            income_columns[canonical_name(value)] = col
    source_base = source_document(
        source_path,
        publisher=common["reit_name"],
        title=f"第{period['period_no']}期 物件毎データ",
        period=period["period"],
        as_of_date=period["as_of_date"],
        url=common["library_url"],
        download_url=period["download_url"],
    )
    snapshots, issues = [], []
    region_labels = {1: "東京都心部", 2: "東京周辺都市部", 3: "地方都市部"}
    row = header_row + 1
    while row <= header_row + 200:
        region_code, name_value, address_value = cell(portfolio, 1, row), cell(portfolio, 2, row), cell(portfolio, 3, row)
        is_region_total = clean_name(name_value) in {"東京都心部", "東京周辺都市部", "地方都市部"}
        if region_code in {1, 2, 3} and not is_region_total and address_value and number_or_none(cell(portfolio, 4, row)) is not None:
            name = clean_name(name_value)
            key = canonical_name(name)
            income_col = income_columns.get(key)
            if income_col is None:
                issues.append({"period": period["period"], "property": name, "field": "noi", "message": "収益シートの列を照合できません"})
            cap, occupancy = percent_from_fraction(cell(portfolio, 11, row)), number_or_none(cell(portfolio, 10, row))
            if cap is not None and not 0 < cap < 20:
                issues.append({"period": period["period"], "property": name, "field": "cap", "value": cap, "message": "想定範囲外"})
            if occupancy is not None and not 0 <= occupancy <= 100:
                issues.append({"period": period["period"], "property": name, "field": "occupancy", "value": occupancy, "message": "0〜100の範囲外"})
            source_cells = {
                "address": f"{portfolio_name}!C{row}", "price": f"{portfolio_name}!D{row}",
                "book_value": f"{portfolio_name}!E{row}", "appraisal": f"{portfolio_name}!F{row}",
                "leasable_area": f"{portfolio_name}!G{row}", "leased_area": f"{portfolio_name}!H{row}",
                "tenants": f"{portfolio_name}!I{row}", "occupancy": f"{portfolio_name}!J{row}",
                "cap": f"{portfolio_name}!K{row}", "discount_rate": f"{portfolio_name}!L{row}",
                "terminal_cap_rate": f"{portfolio_name}!M{row}",
                "noi": f"{income_name}!{col_name(income_col)}{noi_row}" if income_col else None
            }
            source = {**source_base, "cells": source_cells}
            record = {
                "key": key, "name": name, "reit": common["reit_name"], "reit_code": common["reit_code"],
                "type": "オフィス", "region": region_labels.get(region_code), "address": str(address_value).strip(),
                "period_no": period["period_no"], "period": period["period"], "as_of_date": period["as_of_date"],
                "price": million_yen(cell(portfolio, 4, row)), "book_value": million_yen(cell(portfolio, 5, row)),
                "appraisal": million_yen(cell(portfolio, 6, row)), "leasable_area": number_or_none(cell(portfolio, 7, row)),
                "leased_area": number_or_none(cell(portfolio, 8, row)), "tenants": number_or_none(cell(portfolio, 9, row)),
                "occupancy": occupancy, "cap": cap, "discount_rate": percent_from_fraction(cell(portfolio, 12, row)),
                "terminal_cap_rate": percent_from_fraction(cell(portfolio, 13, row)),
                "noi": number_or_none(cell(income, income_col, noi_row)) if income_col else None,
                "source": source,
            }
            record["evidence"] = metric_evidence(record, source, source_cells, parser_name="nbf_excel")
            snapshots.append(record)
        row += 1
    reconciliation = source_reconciliation(portfolio, total_row, snapshots)
    for field, item in reconciliation.items():
        if item["status"] == "review":
            issues.append({"period": period["period"], "field": field, "message": "個別物件合計と原本集計の差が許容範囲外", "difference": item["difference"]})
    report = {"period_no": period["period_no"], "period": period["period"], "properties": len(snapshots),
              "with_noi": sum(item["noi"] is not None for item in snapshots), "reconciliation": reconciliation}
    return snapshots, report, issues


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--accept-source-terms", action="store_true", help="原本の利用上の注意を確認したうえでローカル変換を実行")
    parser.add_argument("--skip-geocode", action="store_true")
    parser.add_argument("--refresh", action="store_true", help="全期間の原本を再ダウンロード")
    parser.add_argument("--no-promote", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if not args.accept_source_terms:
        print("中止: NBF原本の『ご利用上の注意』を確認後、--accept-source-terms を付けて実行してください。", file=sys.stderr)
        return 2

    common = json.loads((ROOT / "config/sources.json").read_text(encoding="utf-8"))["nbf"]
    ensure_private_dirs()
    raw_dir, data_dir = RAW_DIR, NORMALIZED_DIR
    all_snapshots, period_reports, issues = [], [], []
    for period in common["periods"]:
        source_path = raw_dir / period["local_filename"]
        if args.refresh or not source_path.exists():
            print(f"download: {period['period']}", file=sys.stderr)
            source_path.write_bytes(request_bytes(period["download_url"]))
        snapshots, report, period_issues = parse_period(source_path, period, common)
        all_snapshots.extend(snapshots); period_reports.append(report); issues.extend(period_issues)

    latest_no = max(item["period_no"] for item in common["periods"])
    latest = [item for item in all_snapshots if item["period_no"] == latest_no]
    history_by_key = {}
    for snapshot in all_snapshots:
        history_by_key.setdefault(snapshot["key"], []).append(snapshot)
    cache_path = CACHE_DIR / "geocode-cache.json"
    cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
    properties = []
    for current in latest:
        geo = {"lat": None, "lng": None, "matched_address": None, "quality": "not_run", "provider": None}
        if not args.skip_geocode:
            geo = geocode(current["address"], cache)
        history = sorted(history_by_key.get(current["key"], []), key=lambda item: item["as_of_date"])
        public_current = {key: value for key, value in current.items() if key != "key"}
        public_history = [{key: value for key, value in item.items() if key not in {"key", "name", "reit", "reit_code", "type", "region", "address"}}
                          for item in history]
        stable_hash = hashlib.sha1(current["key"].encode("utf-8")).hexdigest()[:10].upper()
        properties.append({"id": f"NBF-{stable_hash}", **public_current, "lat": geo["lat"], "lng": geo["lng"],
                           "geocode": geo, "periods": public_history})
    if not args.skip_geocode:
        cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")

    latest_period = next(item for item in common["periods"] if item["period_no"] == latest_no)
    payload = {
        "meta": {"dataset": "nbf-official-local", "label": f"NBF 第{latest_no}期・過去{len(common['periods'])}期",
                 "reit_code": common["reit_code"], "as_of_date": latest_period["as_of_date"],
                 "periods": len(common["periods"]), "generated_at": datetime.now(timezone.utc).isoformat(),
                 "source_url": common["library_url"],
                 "notice": "NBF公式ファイルを利用者のMac内で変換したローカル分析用データ。公開・再配布しないでください。"},
        "properties": properties
    }
    report = {"current_properties": len(properties), "periods": len(period_reports), "snapshots": len(all_snapshots),
              "with_coordinates": sum(item["lat"] is not None for item in properties),
              "history_points": {str(length): sum(len(item["periods"]) == length for item in properties)
                                 for length in range(1, len(common["periods"]) + 1)},
              "period_reports": period_reports, "issues": issues}
    (data_dir / "nbf-properties.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    if not args.no_promote:
        (data_dir / "properties.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (REPORTS_DIR / "import-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if len(properties) > 0 and not issues else 1


if __name__ == "__main__":
    raise SystemExit(main())
