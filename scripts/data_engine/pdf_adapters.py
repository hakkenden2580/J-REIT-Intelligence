"""Base adapter for PDF sources kept under local private-data."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from evidence import sha256_file

from .contracts import AdapterResult, ImportContext, SourceAdapter, SourceAsset
from .pdf import PDF_MEDIA_TYPE, inspect_pdf_layout, validate_pdf_layout


class LocalPdfAdapter(SourceAdapter):
    """Run a deterministic, source-specific parser after generic PDF gates."""

    def __init__(
        self,
        *,
        source_key: str,
        config: dict,
        parser: Callable[[Path, dict, dict], tuple[dict, dict]],
        adapter_version: str = "0.9.0",
    ) -> None:
        self.source_key = source_key
        self.adapter_id = f"{source_key}_pdf"
        self.adapter_version = adapter_version
        self.config = config
        self.parser = parser

    def run(self, context: ImportContext) -> AdapterResult:
        filename = Path(self.config["local_filename"])
        if filename.is_absolute() or ".." in filename.parts:
            raise ValueError("PDF local_filename must be relative to private-data/raw")
        path = (context.raw_dir / filename).resolve()
        if not path.is_relative_to(context.raw_dir.resolve()):
            raise ValueError("PDF source escaped private-data/raw")
        if not path.is_file():
            raise FileNotFoundError(f"PDF source not found under private-data/raw: {filename}")

        layout = inspect_pdf_layout(path)
        validation = validate_pdf_layout(
            layout,
            min_pages=int(self.config.get("min_pages", 1)),
            max_pages=self.config.get("max_pages"),
            min_text_pages=int(self.config.get("min_text_pages", 1)),
            required_table_pages=tuple(self.config.get("required_table_pages", ())),
        )
        layout_report = {"local_filename": path.name, **layout, "validation": validation}
        if validation["status"] != "compatible":
            raise ValueError(f"{self.source_key}: PDF layout {validation['status']}: {validation['reasons']}")

        payload, report = self.parser(path, self.config, layout)
        report = {
            **report,
            "adapter_id": self.adapter_id,
            "adapter_version": self.adapter_version,
            "layout_fingerprint": layout["fingerprint"],
        }
        output_filename = Path(self.config.get("output_filename", f"{self.source_key}-properties.json"))
        if output_filename.is_absolute() or ".." in output_filename.parts:
            raise ValueError("PDF output_filename must be relative to private-data/normalized")
        output_path = (context.normalized_dir / output_filename).resolve()
        if not output_path.is_relative_to(context.normalized_dir.resolve()):
            raise ValueError("PDF output escaped private-data/normalized")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        asset = SourceAsset(
            source_key=self.source_key,
            local_filename=path.name,
            sha256=sha256_file(path),
            media_type=PDF_MEDIA_TYPE,
            publisher=self.config["publisher"],
            title=self.config["title"],
            period=self.config.get("period"),
            as_of_date=self.config.get("as_of_date"),
            url=self.config.get("url", "https://example.invalid/private-source"),
            download_url=self.config.get("download_url", "https://example.invalid/private-source"),
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
