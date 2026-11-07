#!/usr/bin/env python3
"""Guardrail: a synchronous action must never run on the event loop (#6355).

`registry.invoke` is the single synchronous write choke point — validate,
execute, audit, emit. An `async def` route that calls it directly blocks the
event loop for the duration of the action: the change stream, `/api/health`
polling and every other client wait behind one slow write. The sanctioned
shapes are the ones the codebase already uses:

    result = await asyncio.to_thread(registry.invoke, db, "note.create", p, ctx)
    result = await run_in_threadpool(registry.invoke, db, "note.create", p, ctx)
    @off_loop
    def create_note(...):          # the whole handler off the loop (#5843)

The scan is AST-based over `fichero-server/src/fichero_server/api/routes/`.
An offender is a `registry.invoke` call whose innermost enclosing function is
an `async def`, with no lambda or comprehension between, and no
`to_thread` / `run_in_threadpool` ancestor call. A call inside a nested sync
`def` is judged at the helper's own call site instead — the helper is the
thing that runs on (or off) the loop.

Usage:
    scripts/check_no_sync_invoke_in_async_route.py
    scripts/check_no_sync_invoke_in_async_route.py --list
    scripts/check_no_sync_invoke_in_async_route.py --self-test
    scripts/check_no_sync_invoke_in_async_route.py --help

Exit codes:
    0  no synchronous `registry.invoke` on the event loop
    1  at least one offender
    2  blind — the scan resolved fewer files than its floor
"""

from __future__ import annotations

import ast
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator

from _check_floor import require_scan_floor
from _scan_files import scan_rglob

ROOT = Path(__file__).resolve().parent.parent
SCANNED_ROOTS = (ROOT / "fichero-server" / "src" / "fichero_server" / "api" / "routes",)

WRAP_CALLS = {"to_thread", "run_in_threadpool"}
FUNCTIONS = (ast.AsyncFunctionDef, ast.FunctionDef, ast.Lambda)


@dataclass(frozen=True)
class Offender:
    rel_path: str
    line: int
    handler: str

    @property
    def key(self) -> str:
        return f"{self.rel_path}:{self.line}"

    def __str__(self) -> str:
        return f"{self.key}: {self.handler}"


def _rel(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _iter_python_files(roots: Iterable[Path]) -> Iterator[Path]:
    for root in roots:
        if root.exists():
            yield from sorted(scan_rglob(root, "*.py"))


def _is_invoke(call: ast.Call) -> bool:
    func = call.func
    return (
        isinstance(func, ast.Attribute)
        and func.attr == "invoke"
        and isinstance(func.value, ast.Name)
        and func.value.id == "registry"
    )


def _callee_name(node: ast.AST) -> str | None:
    func = getattr(node, "func", None)
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return None


def _scan_source(rel_path: str, source: str) -> list[Offender]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    parent = {c: p for p in ast.walk(tree) for c in ast.iter_child_nodes(p)}
    offenders: list[Offender] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not _is_invoke(node):
            continue
        ancestors: list[ast.AST] = []
        cur = node
        while cur in parent:
            cur = parent[cur]
            ancestors.append(cur)
        # A call inside a to_thread/run_in_threadpool argument list is already
        # threaded: the worker thread owns it.
        if any(isinstance(a, ast.Call) and _callee_name(a) in WRAP_CALLS for a in ancestors):
            continue
        # Innermost enclosing function: the first one above the direct parent.
        inner = None
        for a in ancestors:
            if isinstance(a, FUNCTIONS):
                inner = a
                break
        if not isinstance(inner, ast.AsyncFunctionDef):
            continue
        offenders.append(Offender(rel_path, node.lineno, inner.name))

    return sorted(offenders, key=lambda o: o.line)


def offenders() -> list[Offender]:
    found: list[Offender] = []
    for path in _iter_python_files(SCANNED_ROOTS):
        rel = _rel(path)
        found.extend(_scan_source(rel, path.read_text(encoding="utf-8", errors="ignore")))
    return found


# ---------------------------------------------------------------------------
# Self-test: the rule must FIRE on the shapes it claims to catch and PASS on
# the sanctioned ones.
# ---------------------------------------------------------------------------

_FIRES = (
    (
        "assigned result",
        'async def h():\n    result = registry.invoke(db, "note.create", p, ctx)\n',
    ),
    (
        "bare statement",
        'async def h():\n    registry.invoke(db, "note.delete", p, ctx)\n',
    ),
    (
        "returned",
        'async def h():\n    return registry.invoke(db, "note.create", p, ctx)\n',
    ),
    (
        "embedded in an expression",
        'async def h():\n    return Started(**registry.invoke(db, "job.start", p, ctx).result)\n',
    ),
    (
        "keyword argument",
        'async def h():\n    registry.invoke(db, "note.create", p, ctx, inverse_of="note.delete")\n',
    ),
)

_PASSES = (
    (
        "asyncio.to_thread",
        'async def h():\n    result = await asyncio.to_thread(registry.invoke, db, "note.create", p, ctx)\n',
    ),
    (
        "run_in_threadpool",
        "async def h():\n    result = await run_in_threadpool(registry.invoke, db, 'note.create', p, ctx)\n",
    ),
    (
        "lambda inside to_thread",
        'async def h():\n    await asyncio.to_thread(lambda: registry.invoke(db, "job.start", p, ctx))\n',
    ),
    (
        "plain def handler",
        'def h():\n    result = registry.invoke(db, "note.create", p, ctx)\n',
    ),
    (
        "nested sync helper, judged at its call site",
        'async def h():\n    def helper():\n        return registry.invoke(db, "note.create", p, ctx)\n'
        "    return await asyncio.to_thread(helper)\n",
    ),
    (
        "module level, not a route",
        'def h():\n    pass\n\nresult = registry.invoke(db, "note.create", p, ctx)\n',
    ),
    (
        "in a comment",
        'async def h():\n    # registry.invoke(db, "note.create", p, ctx) used to live here\n',
    ),
    (
        "in a docstring",
        'async def h():\n    """Calls registry.invoke via to_thread, never direct."""\n',
    ),
    (
        "different receiver",
        'async def h():\n    other.invoke(db, "note.create", p, ctx)\n',
    ),
)


def _self_test() -> None:
    for label, source in _FIRES:
        found = _scan_source("probe.py", source)
        assert found, f"rule FAILED to fire on {label}:\n{source}"
    for label, source in _PASSES:
        found = _scan_source("probe.py", source)
        assert not found, f"rule wrongly fired on {label}: {[str(f) for f in found]}"

    # A real offender in a real tree is reported with its path and line.
    found = _scan_source(
        "fichero-server/src/fichero_server/api/routes/x.py",
        'async def create_note():\n    result = registry.invoke(db, "note.create", p, ctx)\n',
    )
    assert [f.key for f in found] == [
        "fichero-server/src/fichero_server/api/routes/x.py:2"
    ], found


def main() -> int:
    if "--help" in sys.argv or "-h" in sys.argv:
        print(__doc__)
        return 0

    _self_test()
    if "--self-test" in sys.argv:
        print("check_no_sync_invoke_in_async_route self-test: OK")
        return 0

    found = offenders()

    if "--list" in sys.argv:
        for offender in found:
            print(offender)
        print()

    scanned = sum(1 for _ in _iter_python_files(SCANNED_ROOTS))
    # Tripwire, not a ratchet: 173 route files on 2026-11-07, halved.
    require_scan_floor(scanned, 86, "route files (173 on 2026-11-07)")

    if not found:
        print(f"check_no_sync_invoke_in_async_route: OK ({scanned} files, 0 sync invokes on the loop)")
        return 0

    print("Synchronous registry.invoke calls on the event loop (#6355):")
    for offender in found:
        print(f"  {offender}")
    print()
    print("Fix: await asyncio.to_thread(registry.invoke, ...) — the shape ingest/iiif.py uses.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
