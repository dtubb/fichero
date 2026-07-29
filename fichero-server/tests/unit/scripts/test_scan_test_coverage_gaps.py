from __future__ import annotations

import sys
import importlib.util
from pathlib import Path


_SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "scan_test_coverage_gaps.py"
_SPEC = importlib.util.spec_from_file_location("scan_test_coverage_gaps", _SCRIPT)
assert _SPEC and _SPEC.loader
scan_test_coverage_gaps = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = scan_test_coverage_gaps  # register so @dataclass can resolve its module
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
        "… and 1 more" in body
        and "run `python3 scripts/scan_test_coverage_gaps.py` for the full list)." in body
    )
    assert body.count("\n- ") == 200


def test_coverage_predicate_matches_term():
    assert scan_test_coverage_gaps._is_covered("covered", {"covered", "other"})
    assert not scan_test_coverage_gaps._is_covered("missing", {"covered", "other"})


def test_collect_gaps_excludes_covered_symbols(tmp_path):
    source_file = tmp_path / "fichero-server" / "src" / "fichero" / "core" / "sample.py"
    source_file.parent.mkdir(parents=True)
    source_file.write_text(
        """
def covered_symbol():
    pass

def missing_symbol():
    pass
""",
        encoding="utf-8",
    )

    test_file = tmp_path / "fichero-server" / "tests" / "test_sample.py"
    test_file.parent.mkdir(parents=True)
    test_file.write_text("def test_covered_symbol():\n    covered_symbol()\n", encoding="utf-8")

    gaps = scan_test_coverage_gaps._collect_gaps(
        root=tmp_path,
        test_paths=[test_file],
        python_symbol_paths=[source_file],
        swift_symbol_paths=[],
    )
    assert [symbol.name for symbol in gaps["python/core"]] == ["missing_symbol"]
