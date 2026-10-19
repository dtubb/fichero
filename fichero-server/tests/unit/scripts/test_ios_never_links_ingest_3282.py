"""`ios.import-is-copy-only` (#3282): the iPhone companion uploads; it never asks the engine to LINK a path.

WHY: LINK is a macOS security-scoped bookmark on the ENGINE's filesystem; a file picked on an iPhone is invisible to a
Mac-hosted engine, so a LINK from the phone would leave a dangling bookmark. Everything the phone adds goes through the
capture queue's upload (`MobileCaptureQueue`), so none of the iOS-only files may name an ingest mode or call an ingest
route.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

APP = Path(__file__).resolve().parents[4] / "fichero" / "fichero"
# scripts/ is not a package: load the repo's scan helper by path (see test_scan_files_skips_nested_worktrees).
_SCAN = Path(__file__).resolve().parents[4] / "scripts" / "_scan_files.py"
_spec = importlib.util.spec_from_file_location("_scan_files", _SCAN)
assert _spec and _spec.loader
scan_files = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(scan_files)
FORBIDDEN = re.compile(r"IngestMode|\.ingestFolder|ingestFolderApi|ingestFileApi|startFolderImport|ImportService\b")


def _ios_only_files() -> list[Path]:
    files = [APP / "FicheroApp_iOS.swift", *scan_files.scan_rglob(APP, "MobileCapture*.swift")]
    files += [p for p in scan_files.scan_rglob(APP, "*.swift") if re.search(r"(IOS|iOS)[A-Za-z]*\.swift$", p.name)]
    return sorted(set(files))


def test_there_are_ios_only_files_to_check():
    assert len(_ios_only_files()) >= 10


def test_no_ios_only_file_constructs_an_engine_ingest_or_a_link():
    hits = [f"{p.relative_to(APP)}:{n}" for p in _ios_only_files()
            for n, line in enumerate(p.read_text().splitlines(), 1) if FORBIDDEN.search(line)]
    assert hits == [], "iOS-only code must upload (MobileCaptureQueue), never ingest/LINK: " + ", ".join(hits)
