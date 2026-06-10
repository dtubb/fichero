from __future__ import annotations

import importlib.util
from pathlib import Path


_SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "scan_test_coverage_gaps.py"
_SPEC = importlib.util.spec_from_file_location("scan_test_coverage_gaps", _SCRIPT)
assert _SPEC and _SPEC.loader
scan_test_coverage_gaps = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(scan_test_coverage_gaps)  # type: ignore[attr-defined]


def test_is_excluded_drops_generated_code_paths_and_suffixes():
    assert scan_test_coverage_gaps._is_excluded("pkg/generated/file.py", "file.py")
    assert scan_test_coverage_gaps._is_excluded(".build/cache.py", "cache.py")
    assert scan_test_coverage_gaps._is_excluded("pkg/file_generated.py", "file_generated.py")
    assert scan_test_coverage_gaps._is_excluded("pkg/file_generated.swift", "file_generated.swift")
    assert not scan_test_coverage_gaps._is_excluded("pkg/core/file.py", "file.py")


def test_top_module_returns_top_package_or_root():
    assert scan_test_coverage_gaps._top_module("core/api/types.py") == "core"
    assert scan_test_coverage_gaps._top_module("routes.py") == "<root>"


def test_build_issue_body_applies_cap():
    symbols = [
        scan_test_coverage_gaps.SymbolEntry(
            module="python/core",
            file=f"core/{idx}.py",
            kind="func",
            name=f"symbol_{idx}",
        )
        for idx in range(201)
    ]

    body = scan_test_coverage_gaps._build_issue_body("python/core", symbols)
    assert (
        "... and 1 more" in body
        and "run `python3 scripts/scan_test_coverage_gaps.py` for the full list)." in body
    )
    assert body.count("\n- ") == 201


def test_coverage_predicate_matches_term():
    assert scan_test_coverage_gaps._is_covered("covered", {"covered", "other"})
    assert not scan_test_coverage_gaps._is_covered("missing", {"covered", "other"})


def test_collect_gaps_excludes_covered_symbols(monkeypatch):
    monkeypatch.setattr(
        scan_test_coverage_gaps,
        "_scan_python_symbols",
        lambda: [
            scan_test_coverage_gaps.SymbolEntry(
                module="python/core",
                file="core/covered.py",
                kind="func",
                name="covered_symbol",
            ),
            scan_test_coverage_gaps.SymbolEntry(
                module="python/core",
                file="core/missing.py",
                kind="func",
                name="missing_symbol",
            ),
        ],
    )
    monkeypatch.setattr(scan_test_coverage_gaps, "_scan_swift_symbols", lambda: [])
    monkeypatch.setattr(scan_test_coverage_gaps, "_test_terms", lambda: {"covered_symbol"})

    gaps = scan_test_coverage_gaps._collect_gaps()
    assert "python/core" in gaps
    assert len(gaps["python/core"]) == 1
    assert gaps["python/core"][0].name == "missing_symbol"
