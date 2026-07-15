#!/usr/bin/env python3
"""Move legacy local-only files into the private-data layout."""

from __future__ import annotations

import shutil
from pathlib import Path

from runtime_paths import CACHE_DIR, NORMALIZED_DIR, RAW_DIR, REPORTS_DIR, ROOT, ensure_private_dirs

NORMALIZED_FILES = {
    "properties.json",
    "nbf-properties.json",
    "jre-properties.json",
    "glp-properties.json",
}
REPORT_FILES = {"import-report.json", "all-import-report.json"}
CACHE_FILES = {"geocode-cache.json"}


def move_if_present(source: Path, destination: Path) -> bool:
    if not source.exists():
        return False
    if destination.exists():
        if source.read_bytes() == destination.read_bytes():
            source.unlink()
            return True
        raise FileExistsError(f"移行先に異なるファイルがあります: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(destination))
    return True


def main() -> int:
    ensure_private_dirs()
    moved = []
    legacy_raw = ROOT / "sources" / "raw"
    if legacy_raw.exists():
        for source in sorted(legacy_raw.iterdir()):
            if source.is_file() and move_if_present(source, RAW_DIR / source.name):
                moved.append(str(source.relative_to(ROOT)))
    legacy_data = ROOT / "data"
    for name in sorted(NORMALIZED_FILES):
        if move_if_present(legacy_data / name, NORMALIZED_DIR / name):
            moved.append(f"data/{name}")
    for name in sorted(REPORT_FILES):
        if move_if_present(legacy_data / name, REPORTS_DIR / name):
            moved.append(f"data/{name}")
    for name in sorted(CACHE_FILES):
        if move_if_present(legacy_data / name, CACHE_DIR / name):
            moved.append(f"data/{name}")
    print("移行完了:" if moved else "移行対象なし:")
    for item in moved:
        print(f"- {item}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

