#!/usr/bin/env python3
"""Local-only runtime paths for licensed/public source data.

The default keeps private-data inside the worktree for development speed, while
the whole directory remains ignored by Git. Set PIP_PRIVATE_DATA_DIR before
starting an importer/server to move it outside the worktree without code changes.
"""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRIVATE_DATA_DIR = Path(
    os.environ.get("PIP_PRIVATE_DATA_DIR", ROOT / "private-data")
).expanduser().resolve()
RAW_DIR = PRIVATE_DATA_DIR / "raw"
NORMALIZED_DIR = PRIVATE_DATA_DIR / "normalized"
CACHE_DIR = PRIVATE_DATA_DIR / "cache"
REPORTS_DIR = PRIVATE_DATA_DIR / "reports"
QUARANTINE_DIR = PRIVATE_DATA_DIR / "quarantine"


def ensure_private_dirs() -> None:
    for path in (RAW_DIR, NORMALIZED_DIR, CACHE_DIR, REPORTS_DIR, QUARANTINE_DIR):
        path.mkdir(parents=True, exist_ok=True)

