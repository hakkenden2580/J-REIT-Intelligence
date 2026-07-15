"""Property Intelligence Platform Data Engine v0.8 public contracts."""

from .contracts import AdapterResult, ImportContext, SourceAdapter, SourceAsset
from .excel_adapters import NbfWorkbookSetAdapter, SingleWorkbookExcelAdapter
from .registry import AdapterRegistry
from .runner import execute_import_run
from .quality import evaluate_dataset
from .change_detection import archive_snapshot, compare_datasets, semantic_fingerprint

__all__ = [
    "AdapterRegistry",
    "AdapterResult",
    "ImportContext",
    "NbfWorkbookSetAdapter",
    "SingleWorkbookExcelAdapter",
    "SourceAdapter",
    "SourceAsset",
    "archive_snapshot",
    "compare_datasets",
    "evaluate_dataset",
    "execute_import_run",
    "semantic_fingerprint",
]
