#!/usr/bin/env python3
"""Backlog generator for uncovered public symbols.

Heuristic coverage definition:
    A public symbol is considered covered when its bare name appears in a test file.

Default behavior (`--dry-run` or no flags) prints grouped untested symbols and
totals. It never writes issues.

Use `--file-issues` only from the manager lane:
  - one issue per module/area under milestone "Test Coverage" (#82)
  - label `type:test`
  - idempotent by title
  - ratcheting via `scripts/.test_coverage_baseline.json`

Usage:
    python3 scripts/scan_test_coverage_gaps.py
    python3 scripts/scan_test_coverage_gaps.py --dry-run
    python3 scripts/scan_test_coverage_gaps.py --file-issues
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY_ROOT = ROOT / "fichero-server" / "src" / "fichero_server"
SWIFT_ROOT = ROOT / "fichero" / "fichero"
PY_TEST_ROOT = ROOT / "fichero-server" / "tests"
CLI_ROOT = ROOT / "fichero" / "fichero-cli"
BASELINE_FILE = ROOT / "scripts" / ".test_coverage_baseline.json"
MILESTONE_NUMBER = 82
# `gh issue create --milestone` resolves by TITLE, not number.
MILESTONE_TITLE = "Test Coverage"
ISSUE_LABEL = "type:test"

PY_SYMBOL_RE = re.compile(r"^\s*(def|class)\s+([A-Za-z_][A-Za-z0-9_]*)")
SWIFT_SYMBOL_RE = re.compile(
    r"^\s*(?:(?:public|internal|fileprivate|private|open)\s+)?"
    r"(?:(?:@[\w\.\(\)\s\",:=<>\\+-]*)\s+)?"
    r"(func|struct|class|enum|actor)\s+([A-Za-z_][A-Za-z0-9_]*)"
)
WORD_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\b")
TOKEN_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\b")


@dataclass(frozen=True)
class SymbolEntry:
    module: str
    file: str
    kind: str
    name: str

    @property
    def key(self) -> str:
        return f"{self.file}::{self.name}"


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def _python_tests(
    *,
    root: Path | None = None,
    py_test_root: Path | None = None,
    cli_root: Path | None = None,
) -> list[Path]:
    base_root = root or ROOT
    tests_root = py_test_root or base_root / "fichero-server" / "tests"
    cli_tests_root = cli_root or base_root / "fichero" / "fichero-cli"
    tests = sorted(tests_root.rglob("*.py"))
    cli_tests = (
        sorted((cli_tests_root / "tests").rglob("*.py"))
        if (cli_tests_root / "tests").exists()
        else []
    )
    tests.extend(p for p in cli_tests if p not in tests)
    return tests


def _swift_tests(*, root: Path | None = None, swift_root: Path | None = None) -> list[Path]:
    base_root = root or ROOT
    tests_root = swift_root or base_root / "fichero" / "fichero"
    if not tests_root.exists():
        return []
    return sorted(tests_root.glob("**/*Tests/**/*.swift"))


def _test_terms(*, root: Path | None = None, paths: list[Path] | None = None) -> set[str]:
    base_root = root or ROOT
    test_paths = paths if paths is not None else _python_tests(root=base_root) + _swift_tests(root=base_root)
    terms: set[str] = set()
    for path in test_paths:
        try:
            terms.update(TOKEN_RE.findall(_read_text(path)))
        except OSError:
            continue
    return terms


# Paths that are auto-generated or non-product — never flagged for test coverage.
EXCLUDE_SUBSTR = ("/generated/", "/.build/", "/migrations/")


def _is_excluded(rel: str, filename: str) -> bool:
    if any(part in f"/{rel}" for part in EXCLUDE_SUBSTR):
        return True
    if filename.endswith("_generated.py") or filename.endswith("_generated.swift"):
        return True
    return False


def _top_module(rel: str) -> str:
    """Coarse group key: top-level package under the source root."""
    return rel.split("/", 1)[0] if "/" in rel else "<root>"


def _scan_python_symbols(
    *,
    root: Path | None = None,
    py_root: Path | None = None,
    paths: list[Path] | None = None,
) -> list[SymbolEntry]:
    base_root = root or ROOT
    source_root = py_root or base_root / "fichero-server" / "src" / "fichero_server"
    entries: list[SymbolEntry] = []
    for path in paths if paths is not None else sorted(source_root.rglob("*.py")):
        if path.name.startswith("_"):
            continue
        try:
            rel = path.relative_to(source_root).as_posix()
        except ValueError:
            rel = path.as_posix()
        if _is_excluded(rel, path.name):
            continue
        module = _top_module(rel)
        try:
            source = _read_text(path)
        except OSError:
            continue
        for line in source.splitlines():
            m = PY_SYMBOL_RE.match(line)
            if not m:
                continue
            kind, name = m.groups()
            if name.startswith("_"):
                continue
            if m is None:
                continue
            entries.append(SymbolEntry(module=f"python/{module}", file=rel, kind=kind, name=name))
    return entries


def _scan_swift_symbols(
    *,
    root: Path | None = None,
    swift_root: Path | None = None,
    paths: list[Path] | None = None,
) -> list[SymbolEntry]:
    base_root = root or ROOT
    source_root = swift_root or base_root / "fichero" / "fichero"
    entries: list[SymbolEntry] = []
    if paths is None and not source_root.exists():
        return entries

    for path in paths if paths is not None else sorted(source_root.rglob("*.swift")):
        try:
            rel = path.relative_to(source_root).as_posix()
        except ValueError:
            rel = path.as_posix()
        if rel.startswith(".") or _is_excluded(rel, path.name):
            continue
        module = _top_module(rel)
        try:
            lines = _read_text(path).splitlines()
        except OSError:
            continue
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("//"):
                continue
            m = SWIFT_SYMBOL_RE.match(stripped)
            if not m:
                continue
            kind, name = m.groups()
            if re.search(r"\b(private|fileprivate)\b", stripped):
                continue
            entries.append(SymbolEntry(module=f"swift/{module}", file=rel, kind=kind, name=name))
    return entries


def _is_covered(name: str, test_terms: set[str]) -> bool:
    return name in test_terms


def _collect_gaps(
    *,
    root: Path | None = None,
    test_paths: list[Path] | None = None,
    python_symbol_paths: list[Path] | None = None,
    swift_symbol_paths: list[Path] | None = None,
) -> dict[str, list[SymbolEntry]]:
    base_root = root or ROOT
    terms = _test_terms(root=base_root, paths=test_paths)
    by_module: dict[str, list[SymbolEntry]] = {}
    entries = _scan_python_symbols(root=base_root, paths=python_symbol_paths) + _scan_swift_symbols(
        root=base_root,
        paths=swift_symbol_paths,
    )
    for entry in entries:
        if _is_covered(entry.name, terms):
            continue
        by_module.setdefault(entry.module, []).append(entry)
    for symbols in by_module.values():
        symbols.sort(key=lambda s: (s.file, s.kind, s.name))
    return dict(sorted(by_module.items(), key=lambda item: item[0]))


def _dry_run_report(gaps: dict[str, list[SymbolEntry]]) -> int:
    total = sum(len(symbols) for symbols in gaps.values())
    print("coverage-gap scan (dry-run):")
    print(f"  total untested public symbols: {total}")
    for module, symbols in gaps.items():
        print(f"\n  {module}: {len(symbols)}")
        for symbol in symbols:
            print(f"    {symbol.file}::{symbol.kind} {symbol.name}")

    python_total = sum(len(v) for k, v in gaps.items() if k.startswith("python/"))
    swift_total = sum(len(v) for k, v in gaps.items() if k.startswith("swift/"))
    print("\nTotals by layer:")
    print(f"  python: {python_total}")
    print(f"  swift: {swift_total}")
    return 0


def _run_gh(*args: str) -> str:
    result = subprocess.run(
        ["gh", *args],
        check=True,
        text=True,
        capture_output=True,
    )
    return result.stdout.strip()


def _load_baseline() -> dict[str, dict[str, list[str] | int]]:
    if not BASELINE_FILE.exists():
        return {}
    try:
        return json.loads(BASELINE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _save_baseline(state: dict[str, dict[str, list[str] | int]]) -> None:
    BASELINE_FILE.parent.mkdir(parents=True, exist_ok=True)
    BASELINE_FILE.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _find_issue(title: str) -> int | None:
    payload = _run_gh("issue", "list", "--state", "open", "--search", title, "--json", "number,title")
    issues = json.loads(payload) if payload else []
    for issue in issues:
        if issue.get("title") == title:
            return int(issue["number"])
    return None


def _build_issue_body(module: str, symbols: list[SymbolEntry], new_only: list[str] | None = None) -> str:
    lines = [
        f"## Module / area\n`{module}`",
        "",
        "Heuristic scan found these public symbols without test coverage.",
        "",
        "### Untested symbols",
    ]
    if new_only is not None and new_only:
        lines.append("(new since last baseline)")
        lines.append("")
    # Cap the listing so very large groups stay well under GitHub's 64KB body
    # limit; the full set is always reproducible from the scanner.
    cap = 200
    shown = symbols[:cap]
    lines.extend(f"- {symbol.file}::{symbol.kind} {symbol.name}" for symbol in shown)
    if len(symbols) > cap:
        lines.append("")
        lines.append(
            f"… and {len(symbols) - cap} more "
            f"(run `python3 scripts/scan_test_coverage_gaps.py` for the full list)."
        )
    return "\n".join(lines) + "\n"


def _upsert_issue(module: str, symbols: list[SymbolEntry], issue_number: int | None) -> int | None:
    title = f"[Test Coverage] {module} — {len(symbols)} untested symbols"
    new_only = [s.key for s in symbols if True]
    body = _build_issue_body(module, symbols, new_only=new_only)
    if issue_number is None:
        issue_number_json = _find_issue(title)
        issue_number = issue_number_json

    if issue_number is None:
        cmd = [
            "issue",
            "create",
            "--title",
            title,
            "--body",
            body,
            "--milestone",
            MILESTONE_TITLE,
            "--label",
            ISSUE_LABEL,
        ]
        output = _run_gh(*cmd)
        # `gh issue create` prints the issue URL (…/issues/<n>), not "#<n>".
        match = re.search(r"/issues/(\d+)", output) or re.search(r"#(\d+)", output)
        if match:
            return int(match.group(1))
        return None

    if not issue_number:
        # Defensive: never run `gh issue edit 0` from a stale/None tracked number.
        issue_number = _find_issue(title)
        if not issue_number:
            return None

    _run_gh(
        "issue",
        "edit",
        str(issue_number),
        "--title",
        title,
        "--body",
        body,
    )
    return issue_number


def _file_issues(gaps: dict[str, list[SymbolEntry]]) -> int:
    baseline = _load_baseline()
    current: dict[str, dict[str, list[str] | int]] = {}
    created_or_updated = 0

    for module, symbols in gaps.items():
        current_keys = sorted(s.key for s in symbols)
        prior = baseline.get(module, {})
        prior_symbols = set(prior.get("symbols", []))
        new_symbols = sorted(set(current_keys) - set(prior_symbols))
        tracked = prior.get("issue_number")
        issue_number = None
        if isinstance(tracked, int):
            issue_number = tracked
        elif isinstance(tracked, str) and tracked.isdigit():
            issue_number = int(tracked)

        if issue_number is None and not current_keys:
            continue
        issue_number = _upsert_issue(module, symbols, issue_number)
        if issue_number is not None:
            created_or_updated += 1
        current[module] = {"issue_number": issue_number or 0, "symbols": current_keys}
        if new_symbols:
            print(
                f"[new] {module}: {len(new_symbols)} new untested symbols (total {len(current_keys)})"
            )
        else:
            print(f"[known] {module}: {len(current_keys)} untested symbols")

    # Keep ratcheting by removing stale modules from baseline as gaps close.
    for stale_module, data in baseline.items():
        if stale_module not in gaps:
            print(f"[cleaned] {stale_module}: no longer has untested public symbols")
        else:
            # updated above in current
            continue

    _save_baseline(current)
    total = sum(len(v) for v in gaps.values())
    print(f"\ncoverage-gap issues: {created_or_updated} issue(s) upserted, {total} total untested symbols.")
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scan public symbols with no test coverage.")
    parser.add_argument(
        "--file-issues",
        action="store_true",
        help="create/update GitHub issues under milestone #82",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print grouped report without touching issues",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    gaps = _collect_gaps()

    if args.file_issues:
        return _file_issues(gaps)

    return _dry_run_report(gaps)


if __name__ == "__main__":
    raise SystemExit(main())
