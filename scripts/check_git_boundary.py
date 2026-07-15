#!/usr/bin/env python3
"""Fail when local real-data artifacts are tracked by Git."""

from __future__ import annotations

import subprocess
from pathlib import Path

from runtime_paths import ROOT

FORBIDDEN_PREFIXES = ("private-data/", "sources/raw/")
FORBIDDEN_FILES = {
    "data/properties.json",
    "data/nbf-properties.json",
    "data/jre-properties.json",
    "data/glp-properties.json",
    "data/import-report.json",
    "data/all-import-report.json",
    "data/geocode-cache.json",
}
SOURCE_DOCUMENT_SUFFIXES = {".pdf", ".xls", ".xlsx"}


def tracked_files() -> list[str]:
    output = subprocess.check_output(["git", "ls-files"], cwd=ROOT, text=True)
    return [line.strip() for line in output.splitlines() if line.strip()]


def violations(files: list[str]) -> list[str]:
    return sorted(
        path for path in files
        if path in FORBIDDEN_FILES
        or path.startswith(FORBIDDEN_PREFIXES)
        or (Path(path).suffix.lower() in SOURCE_DOCUMENT_SUFFIXES
            and not path.startswith("tests/fixtures/fictional-"))
    )


def main() -> int:
    found = violations(tracked_files())
    if found:
        print("ERROR: 実データ候補がGit管理対象です:")
        for path in found:
            print(f"- {path}")
        return 1
    print("OK: private-data・原本・正規化済み実データはGit管理されていません。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
