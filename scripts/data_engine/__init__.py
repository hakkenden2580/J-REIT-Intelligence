"""Property Intelligence Platform Data Engine v0.10 public contracts."""

from .contracts import AdapterResult, ImportContext, SourceAdapter, SourceAsset
from .excel_adapters import NbfWorkbookSetAdapter, SingleWorkbookExcelAdapter
from .registry import AdapterRegistry
from .runner import execute_import_run
from .quality import evaluate_dataset
from .change_detection import archive_snapshot, compare_datasets, semantic_fingerprint
from .pdf import (PDF_MEDIA_TYPE, PdfDependencyError, PdfTextMatch,
                  extract_page_text, find_labeled_number, find_text,
                  inspect_pdf_layout, validate_pdf_layout)
from .pdf_adapters import LocalPdfAdapter
from .nbf_pdf import LocatedNumber, parse_nbf_earnings_presentation

__all__ = [
    "AdapterRegistry",
    "AdapterResult",
    "ImportContext",
    "LocalPdfAdapter",
    "LocatedNumber",
    "NbfWorkbookSetAdapter",
    "SingleWorkbookExcelAdapter",
    "SourceAdapter",
    "SourceAsset",
    "PDF_MEDIA_TYPE",
    "PdfDependencyError",
    "PdfTextMatch",
    "archive_snapshot",
    "compare_datasets",
    "evaluate_dataset",
    "execute_import_run",
    "extract_page_text",
    "find_labeled_number",
    "find_text",
    "inspect_pdf_layout",
    "parse_nbf_earnings_presentation",
    "semantic_fingerprint",
    "validate_pdf_layout",
]
