#!/usr/bin/env python3
"""Guardrail: no pure-silent broad exception swallow in WRITE paths (#2507).

Daniel's principle: 'silent fallbacks likely cause bugs. I'd rather raise errors
so we see them.' The #2430 corruption (a failed by-id lookup silently rerouting a
write to the parent PDF) and the scheduler remove_job swallow are this class — a
mutation path that catches `except Exception` and does NOTHING observable, so a
genuine failure looks like success.

This is AST static analysis over `fichero-engine/src/fichero/**/*.py`. It flags an
`except Exception:` handler whose body is PURELY silent —

    only `pass` / `continue` / `break` / `...` / bare `return` / `return None`,
    with NO logging call and NO `raise`

— when it sits inside a function whose name implies a WRITE/mutation
(save/upsert/create/update/delete/merge/write/persist/ingest/store). Those are the
paths where a swallowed error masks data loss.

NOT flagged (intentionally narrow, to avoid the over-reach Daniel warned about):
  - Narrow excepts (`except JobLookupError:` etc.) — the expected, handled case.
  - Handlers that LOG (logger.warning/debug/…) then return — the sanctioned
    'log-warn-and-skip' pattern.
  - Handlers that RETURN AN ERROR PAYLOAD (`return Response(error=…)`, a tuple
    carrying the exception) — the error is surfaced to the caller, not hidden.
  - Read/compute functions — only write-named functions are in scope.

Baseline is CLEAN (KNOWN_VIOLATIONS empty): the #2430 save paths return None +
log, browser_save / _ingest_one surface the error, and the scheduler now narrows
to JobLookupError. The check fails the moment a NEW silent write-swallow appears.

Usage:
    scripts/check_silent_write_swallow.py
    scripts/check_silent_write_swallow.py --list
    scripts/check_silent_write_swallow.py --help
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "fichero-engine" / "src" / "fichero"
RULE_DOC = "docs/architecture/swiftui/reform_masterplan_2026-06.md"

WRITE_MARKERS = (
    "save", "upsert", "create", "update", "delete",
    "merge", "write", "persist", "ingest", "store",
)
LOG_HINTS = ("log", "logger", "logging", "warn", "warning", "error", "exception", "print", "capture")

# Clean: every write-path swallow now raises, logs, or surfaces the error.
KNOWN_VIOLATIONS: dict[str, str] = {}


def _is_broad_exception(node: ast.expr | None) -> bool:
    return isinstance(node, ast.Name) and node.id == "Exception"


def _has_log_or_raise(handler: ast.ExceptHandler) -> bool:
    for n in ast.walk(ast.Module(body=handler.body, type_ignores=[])):
        if isinstance(n, ast.Raise):
            return True
        if isinstance(n, ast.Call):
            func = n.func
            name = func.attr.lower() if isinstance(func, ast.Attribute) else (
                func.id.lower() if isinstance(func, ast.Name) else ""
            )
            if any(h in name for h in LOG_HINTS):
                return True
    return False


def _is_pure_silent(handler: ast.ExceptHandler) -> bool:
    """Body is only no-op / bare-return — surfaces nothing about the failure."""
    if _has_log_or_raise(handler):
        return False
    for stmt in handler.body:
        if isinstance(stmt, (ast.Pass, ast.Continue, ast.Break)):
            continue
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant):
            continue  # docstring / `...`
        if isinstance(stmt, ast.Return) and (
            stmt.value is None
            or (isinstance(stmt.value, ast.Constant) and stmt.value.value is None)
        ):
            continue  # bare return / return None — no error payload
        return False  # anything else (return Response(error=…), assignment, …)
    return True


def scan(src: Path = SRC) -> dict[str, str]:
    found: dict[str, str] = {}
    for path in sorted(src.rglob("*.py")):
        if "generated" in path.parts:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
        except SyntaxError:
            continue
        func_by_line: dict[int, str] = {}
        for fn in ast.walk(tree):
            if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for ln in range(fn.lineno, (fn.end_lineno or fn.lineno) + 1):
                    func_by_line[ln] = fn.name
        rel = path.relative_to(src).as_posix()
        for n in ast.walk(tree):
            if not isinstance(n, ast.ExceptHandler):
                continue
            if not _is_broad_exception(n.type) or not _is_pure_silent(n):
                continue
            fname = func_by_line.get(n.lineno, "")
            if any(w in fname.lower() for w in WRITE_MARKERS):
                found[f"{rel}:{n.lineno}"] = f"silent `except Exception` in {fname}()"
    return found


def main() -> int:
    argv = sys.argv[1:]
    if any(a in ("-h", "--help") for a in argv):
        print(__doc__)
        return 0

    found = scan()
    known = set(KNOWN_VIOLATIONS)

    if "--list" in argv:
        print(f"Silent write-path swallows ({len(found)}):\n")
        for key, reason in sorted(found.items()):
            tag = "known" if key in known else "NEW"
            print(f"  [{tag}] {key}  <-  {reason}")
        return 0

    new = sorted(set(found) - known)
    stale = sorted(known - set(found))

    print("Silent write-swallow guardrail (#2507):")
    print(f"  scanned {SRC.relative_to(ROOT)}")
    print(f"  {len(found)} pure-silent broad swallow(s) in write paths; {len(known)} known.")

    if new:
        print(f"\n  ✗ {len(new)} NEW silent swallow(s) masking a write failure:")
        for key in new:
            print(f"      {key}  ←  {found[key]}")
        print(
            "\nFix: raise, log-warn-and-skip with diagnostics, or surface the error "
            "to the caller — never silently swallow a write failure. Narrow the except "
            f"to the expected exception if the no-op is genuinely correct. Rule: {RULE_DOC}."
        )
        return 1

    if stale:
        print(f"\n  ✓ {len(stale)} KNOWN_VIOLATIONS entr(ies) now clean — drop them:")
        for key in stale:
            print(f"      {key}")

    print("\n✓ No silent broad exception swallows in write paths.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
