#!/usr/bin/env python3
"""NBFの公式「物件毎データ」をローカル分析用JSONへ変換する。

外部Pythonパッケージを使わず、xlsx (ZIP/XML) を直接読み取る。
生成データと原本は.gitignore対象で、公開リポジトリへ含めない。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
REL_NS = {"r": "http://schemas.openxmlformats.org/package/2006/relationships"}
DOC_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
GSI_URL = "https://msearch.gsi.go.jp/address-search/AddressSearch"
USER_AGENT = "J-REIT-Intelligence/0.2 local research prototype"


def request_bytes(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as res:
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


def parse_value(cell: ET.Element, strings: list[str]):
    kind = cell.attrib.get("t")
    value = cell.find("m:v", NS)
    if kind == "inlineStr":
        return "".join(t.text or "" for t in cell.findall(".//m:t", NS))
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
            for cell in root.findall(".//m:sheetData/m:row/m:c", NS):
                cells[cell.attrib["r"]] = parse_value(cell, strings)
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


def number_or_none(value):
    return value if isinstance(value, (int, float)) else None


def million_yen(value):
    value = number_or_none(value)
    return round(value / 1_000_000, 3) if value is not None else None


def percent_from_fraction(value):
    value = number_or_none(value)
    return round(value * 100, 3) if value is not None else None


def geocode(address: str, cache: dict[str, object]):
    if address in cache:
        return cache[address]
    url = GSI_URL + "?" + urllib.parse.urlencode({"q": address})
    try:
        results = json.loads(request_bytes(url).decode("utf-8"))
        if results:
            lon, lat = results[0]["geometry"]["coordinates"]
            result = {
                "lat": lat,
                "lng": lon,
                "matched_address": results[0].get("properties", {}).get("title"),
                "quality": "automatic",
                "provider": "GSI AddressSearch"
            }
        else:
            result = {"lat": None, "lng": None, "matched_address": None, "quality": "unknown", "provider": "GSI AddressSearch"}
    except Exception as exc:  # 個別住所の失敗で全体を止めない
        result = {"lat": None, "lng": None, "matched_address": None, "quality": "error", "provider": "GSI AddressSearch", "error": str(exc)}
    cache[address] = result
    time.sleep(0.15)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--accept-source-terms", action="store_true", help="原本の利用上の注意を確認したうえでローカル変換を実行")
    parser.add_argument("--skip-geocode", action="store_true")
    parser.add_argument("--refresh", action="store_true", help="原本を再ダウンロード")
    args = parser.parse_args()
    if not args.accept_source_terms:
        print("中止: NBF原本の『ご利用上の注意』を確認後、--accept-source-terms を付けて実行してください。", file=sys.stderr)
        return 2

    config = json.loads((ROOT / "config/sources.json").read_text(encoding="utf-8"))["nbf"]
    raw_dir, data_dir = ROOT / "sources/raw", ROOT / "data"
    raw_dir.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)
    source_path = raw_dir / config["local_filename"]
    if args.refresh or not source_path.exists():
        source_path.write_bytes(request_bytes(config["download_url"]))

    sheets = read_xlsx(source_path)
    portfolio = sheets["データシート"]
    income = sheets["個別物件の収益状況"]
    income_columns = {clean_name(cell(income, col, 6)): col for col in range(8, 79) if cell(income, col, 6)}

    cache_path = data_dir / "geocode-cache.json"
    cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
    properties, issues = [], []
    region_labels = {1: "東京都心部", 2: "東京周辺都市部", 3: "地方都市部"}
    for row in range(8, 78):
        name = clean_name(cell(portfolio, 2, row))
        if not name:
            continue
        address = str(cell(portfolio, 3, row) or "").strip()
        income_col = income_columns.get(name)
        if income_col is None:
            issues.append({"property": name, "field": "noi", "message": "収益シートの列を照合できませんでした"})
        geo = {"lat": None, "lng": None, "matched_address": None, "quality": "not_run", "provider": None}
        if not args.skip_geocode:
            geo = geocode(address, cache)
        cap = percent_from_fraction(cell(portfolio, 11, row))
        occupancy = number_or_none(cell(portfolio, 10, row))
        if cap is not None and not 0 < cap < 20:
            issues.append({"property": name, "field": "cap", "value": cap, "message": "想定範囲外"})
        if occupancy is not None and not 0 <= occupancy <= 100:
            issues.append({"property": name, "field": "occupancy", "value": occupancy, "message": "0〜100の範囲外"})
        source_cells = {
            "address": f"データシート!C{row}", "price": f"データシート!D{row}",
            "book_value": f"データシート!E{row}", "appraisal": f"データシート!F{row}",
            "leasable_area": f"データシート!G{row}", "leased_area": f"データシート!H{row}",
            "tenants": f"データシート!I{row}", "occupancy": f"データシート!J{row}",
            "cap": f"データシート!K{row}", "discount_rate": f"データシート!L{row}",
            "terminal_cap_rate": f"データシート!M{row}",
            "noi": f"個別物件の収益状況!{col_name(income_col)}20" if income_col else None
        }
        properties.append({
            "id": f"NBF-{row - 7:03d}", "name": name, "reit": config["reit_name"], "reit_code": config["reit_code"],
            "type": "オフィス", "region": region_labels.get(cell(portfolio, 1, row)), "address": address,
            "lat": geo["lat"], "lng": geo["lng"], "geocode": geo,
            "price": million_yen(cell(portfolio, 4, row)), "book_value": million_yen(cell(portfolio, 5, row)),
            "appraisal": million_yen(cell(portfolio, 6, row)), "leasable_area": number_or_none(cell(portfolio, 7, row)),
            "leased_area": number_or_none(cell(portfolio, 8, row)), "tenants": number_or_none(cell(portfolio, 9, row)),
            "occupancy": occupancy, "cap": cap, "discount_rate": percent_from_fraction(cell(portfolio, 12, row)),
            "terminal_cap_rate": percent_from_fraction(cell(portfolio, 13, row)),
            "noi": number_or_none(cell(income, income_col, 20)) if income_col else None,
            "source": {"document": config["document_title"], "period": config["period"], "as_of_date": config["as_of_date"],
                       "url": config["library_url"], "download_url": config["download_url"], "cells": source_cells}
        })

    if not args.skip_geocode:
        cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    sha256 = hashlib.sha256(source_path.read_bytes()).hexdigest()
    payload = {
        "meta": {"dataset": "nbf-official-local", "label": f"NBF {config['period']}", "reit_code": config["reit_code"],
                 "as_of_date": config["as_of_date"], "generated_at": datetime.now(timezone.utc).isoformat(),
                 "source_url": config["library_url"], "source_sha256": sha256,
                 "notice": "NBF公式ファイルを利用者のMac内で変換したローカル分析用データ。公開・再配布しないでください。"},
        "properties": properties
    }
    source_totals = {
        "price": million_yen(cell(portfolio, 4, 4)),
        "book_value": million_yen(cell(portfolio, 5, 4)),
        "appraisal": million_yen(cell(portfolio, 6, 4)),
        "leasable_area": number_or_none(cell(portfolio, 7, 4)),
        "leased_area": number_or_none(cell(portfolio, 8, 4)),
        "tenants": number_or_none(cell(portfolio, 9, 4))
    }
    normalized_totals = {
        key: round(sum((p.get(key) or 0) for p in properties), 3)
        for key in source_totals
    }
    tolerances = {"price": 0.01, "book_value": 0.01, "appraisal": 0.01,
                  "leasable_area": 1, "leased_area": 1, "tenants": 0}
    reconciliation = {}
    for key in source_totals:
        difference = round(normalized_totals[key] - source_totals[key], 3)
        reconciliation[key] = {"source": source_totals[key], "normalized": normalized_totals[key],
                               "difference": difference, "tolerance": tolerances[key],
                               "status": "ok" if abs(difference) <= tolerances[key] else "review"}
        if reconciliation[key]["status"] == "review":
            issues.append({"field": key, "message": "個別物件合計と原本集計の差が許容範囲外", "difference": difference})
    report = {"properties": len(properties), "with_coordinates": sum(p["lat"] is not None for p in properties),
              "with_noi": sum(p["noi"] is not None for p in properties),
              "reconciliation": reconciliation, "issues": issues}
    (data_dir / "properties.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (data_dir / "import-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if len(properties) == 70 else 1


if __name__ == "__main__":
    raise SystemExit(main())
