"""Source Adapter contracts shared by Excel, PDF, XBRL and future adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ImportContext:
    root: Path
    private_data_dir: Path
    raw_dir: Path
    normalized_dir: Path
    cache_dir: Path
    reports_dir: Path
    quarantine_dir: Path
    refresh: bool = False
    shared_state: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SourceAsset:
    source_key: str
    local_filename: str
    sha256: str
    media_type: str
    publisher: str
    title: str
    period: str | None
    as_of_date: str | None
    url: str
    download_url: str
    layout_fingerprint: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_key": self.source_key,
            "local_filename": self.local_filename,
            "sha256": self.sha256,
            "media_type": self.media_type,
            "publisher": self.publisher,
            "title": self.title,
            "period": self.period,
            "as_of_date": self.as_of_date,
            "url": self.url,
            "download_url": self.download_url,
            "layout_fingerprint": self.layout_fingerprint,
        }


@dataclass
class AdapterResult:
    source_key: str
    adapter_id: str
    adapter_version: str
    payload: dict[str, Any]
    report: dict[str, Any]
    source_assets: list[SourceAsset]
    layout_reports: list[dict[str, Any]]
    issues: list[dict[str, Any]] = field(default_factory=list)

    def run_summary(self) -> dict[str, Any]:
        return {
            "source_key": self.source_key,
            "adapter_id": self.adapter_id,
            "adapter_version": self.adapter_version,
            "status": "succeeded",
            "properties": len(self.payload.get("properties", [])),
            "issues": len(self.issues),
            "source_assets": [asset.to_dict() for asset in self.source_assets],
            "layouts": self.layout_reports,
        }


class SourceAdapter(ABC):
    source_key: str
    adapter_id: str
    adapter_version: str

    @abstractmethod
    def run(self, context: ImportContext) -> AdapterResult:
        """Acquire, validate, parse and normalize one logical source."""

    def descriptor(self) -> dict[str, str]:
        return {
            "source_key": self.source_key,
            "adapter_id": self.adapter_id,
            "adapter_version": self.adapter_version,
        }
