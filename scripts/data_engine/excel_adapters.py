"""Excel adapter implementations for the three pilot REITs."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Callable

from evidence import sha256_file

from .contracts import AdapterResult, ImportContext, SourceAdapter, SourceAsset
from .layout import inspect_workbook_layout, validate_workbook_layout

XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _asset(
    *,
    source_key: str,
    path: Path,
    config: dict,
    title: str,
    period: str | None,
    as_of_date: str | None,
    download_url: str,
    layout_fingerprint: str,
) -> SourceAsset:
    return SourceAsset(
        source_key=source_key,
        local_filename=path.name,
        sha256=sha256_file(path),
        media_type=XLSX_MEDIA_TYPE,
        publisher=config["reit_name"],
        title=title,
        period=period,
        as_of_date=as_of_date,
        url=config["library_url"],
        download_url=download_url,
        layout_fingerprint=layout_fingerprint,
    )


class SingleWorkbookExcelAdapter(SourceAdapter):

    def __init__(
        self,
        *,
        source_key: str,
        config: dict,
        parser: Callable[[Path, dict, dict], tuple[dict, dict]],
        request_bytes: Callable[[str], bytes],
        read_xlsx: Callable[[Path], dict[str, dict[str, object]]],
        required_sheets: tuple[str, ...],
        title: str,
        adapter_version: str = "0.6.0",
    ) -> None:
        self.source_key = source_key
        self.adapter_id = f"{source_key}_excel"
        self.config = config
        self.parser = parser
        self.request_bytes = request_bytes
        self.read_xlsx = read_xlsx
        self.required_sheets = required_sheets
        self.title = title
        self.adapter_version = adapter_version

    def run(self, context: ImportContext) -> AdapterResult:
        path = context.raw_dir / self.config["local_filename"]
        if context.refresh or not path.exists():
            path.write_bytes(self.request_bytes(self.config["download_url"]))
        layout = inspect_workbook_layout(self.read_xlsx(path))
        validation = validate_workbook_layout(layout, required_sheets=self.required_sheets)
        layout_report = {"local_filename": path.name, **layout, "validation": validation}
        if validation["status"] != "compatible":
            raise ValueError(f"{self.source_key}: workbook layout incompatible: {validation}")
        payload, report = self.parser(path, self.config, context.shared_state.setdefault("geocode_cache", {}))
        report = {**report, "adapter_id": self.adapter_id, "adapter_version": self.adapter_version,
                  "layout_fingerprint": layout["fingerprint"]}
        (context.normalized_dir / f"{self.source_key}-properties.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        asset = _asset(
            source_key=self.source_key,
            path=path,
            config=self.config,
            title=self.title,
            period=self.config.get("period"),
            as_of_date=self.config.get("as_of_date"),
            download_url=self.config["download_url"],
            layout_fingerprint=layout["fingerprint"],
        )
        return AdapterResult(
            source_key=self.source_key,
            adapter_id=self.adapter_id,
            adapter_version=self.adapter_version,
            payload=payload,
            report=report,
            source_assets=[asset],
            layout_reports=[layout_report],
            issues=list(report.get("issues", [])),
        )


class NbfWorkbookSetAdapter(SourceAdapter):
    source_key = "nbf"
    adapter_id = "nbf_excel"
    adapter_version = "0.8.0"

    def __init__(
        self,
        *,
        config: dict,
        request_bytes: Callable[[str], bytes],
        read_xlsx: Callable[[Path], dict[str, dict[str, object]]],
    ) -> None:
        self.config = config
        self.request_bytes = request_bytes
        self.read_xlsx = read_xlsx

    def run(self, context: ImportContext) -> AdapterResult:
        assets: list[SourceAsset] = []
        layouts: list[dict] = []
        for period in self.config["periods"]:
            path = context.raw_dir / period["local_filename"]
            if context.refresh or not path.exists():
                path.write_bytes(self.request_bytes(period["download_url"]))
            layout = inspect_workbook_layout(self.read_xlsx(path))
            validation = validate_workbook_layout(
                layout,
                required_sheets=("データシート",),
                required_name_fragments=("収益",),
            )
            layout_report = {"local_filename": path.name, **layout, "validation": validation}
            layouts.append(layout_report)
            if validation["status"] != "compatible":
                raise ValueError(f"nbf/{period['period']}: workbook layout incompatible: {validation}")
            assets.append(_asset(
                source_key=self.source_key,
                path=path,
                config=self.config,
                title=f"第{period['period_no']}期 物件毎データ",
                period=period["period"],
                as_of_date=period["as_of_date"],
                download_url=period["download_url"],
                layout_fingerprint=layout["fingerprint"],
            ))
        command = [sys.executable, str(context.root / "scripts/import_nbf.py"),
                   "--accept-source-terms", "--no-promote"]
        environment = {**os.environ, "PIP_PRIVATE_DATA_DIR": str(context.private_data_dir)}
        subprocess.run(command, cwd=context.root, env=environment, check=True, stdout=subprocess.DEVNULL)
        payload = json.loads((context.normalized_dir / "nbf-properties.json").read_text(encoding="utf-8"))
        report = json.loads((context.reports_dir / "import-report.json").read_text(encoding="utf-8"))
        report = {**report, "adapter_id": self.adapter_id, "adapter_version": self.adapter_version,
                  "layout_fingerprints": [item["fingerprint"] for item in layouts]}
        return AdapterResult(
            source_key=self.source_key,
            adapter_id=self.adapter_id,
            adapter_version=self.adapter_version,
            payload=payload,
            report=report,
            source_assets=assets,
            layout_reports=layouts,
            issues=list(report.get("issues", [])),
        )
