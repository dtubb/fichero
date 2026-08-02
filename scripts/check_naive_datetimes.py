#!/usr/bin/env python3
"""Guardrail: no naive wall-clock reads in server source (#4347).

A naive ``datetime.now()`` is *local* time. Serialized without an offset, every
ISO-8601 decoder — the Swift client included — reads it back as UTC, so a row
written at 08:57 ADT rendered as "3 hours ago". ``datetime.utcnow()`` is the
same bug with a friendlier name: it returns the UTC wall clock with **no**
tzinfo, so it is equally indistinguishable from local time downstream.

The one sanctioned clock is ``fichero_server.core.timeutil.utc_now()``, which
returns an aware UTC datetime. This checker fails on the naive forms:

    datetime.now()                       -> utc_now()
    datetime.utcnow()                    -> utc_now()
    Field(default_factory=datetime.now)  -> Field(default_factory=utc_now)
    field(default_factory=datetime.utcnow)

``datetime.now(timezone.utc)``, ``datetime.now(tz=...)`` and
``datetime.now(ZoneInfo(...))`` all pass — an explicit tz argument is the point.

The scan is AST-based, so the naive forms cannot hide in a comment or docstring
and cannot be missed by an alias (``from datetime import datetime as _datetime``
and ``import datetime as dt`` are both resolved to the real symbol).

Usage:
    scripts/check_naive_datetimes.py
    scripts/check_naive_datetimes.py --list
    scripts/check_naive_datetimes.py --self-test
    scripts/check_naive_datetimes.py --help

Exit codes:
    0  no naive clock reads outside the sanctioned definition site
    1  at least one offender, or a stale KNOWN_VIOLATIONS entry to drop
"""

from __future__ import annotations

import ast
import sys

from _check_floor import require_scan_floor
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator

ROOT = Path(__file__).resolve().parent.parent
SCANNED_ROOTS = (
    ROOT / "fichero-server" / "src" / "fichero_server",
    ROOT / "fichero-cli" / "src",
    ROOT / "fichero-mcp" / "src",
)

# The canonical clock lives here and is the ONE place allowed to call the naive
# constructor — ``utc_now()`` is literally ``datetime.now(timezone.utc)``, and
# ``naive_utc()`` deliberately strips the offset for naive-only contracts.
SANCTIONED_FILES = {"fichero-server/src/fichero_server/core/timeutil.py"}

# Keyed "relpath:line" -> reason. Empty on purpose: the #4347 sweep converted
# every site, so a new entry here is a deliberate, reviewed exception rather
# than a place to park new debt.
KNOWN_VIOLATIONS: dict[str, str] = {}

ALLOW_COMMENT = "naive-datetime-guardrail: allow"

_NAIVE_ATTRS = {"now", "utcnow"}


@dataclass(frozen=True)
class Offender:
    rel_path: str
    line: int
    expr: str

    @property
    def key(self) -> str:
        return f"{self.rel_path}:{self.line}"

    def __str__(self) -> str:
        return f"{self.key}: {self.expr}"


def _rel(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _iter_python_files(roots: Iterable[Path]) -> Iterator[Path]:
    for root in roots:
        if root.exists():
            yield from sorted(root.rglob("*.py"))


class _DatetimeNames:
    """Resolve the local names that refer to ``datetime.datetime`` / the module."""

    def __init__(self, tree: ast.AST) -> None:
        # Names bound to the datetime *class* (``from datetime import datetime``).
        self.classes: set[str] = set()
        # Names bound to the datetime *module* (``import datetime``).
        self.modules: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "datetime":
                        self.modules.add(alias.asname or "datetime")
            elif isinstance(node, ast.ImportFrom) and node.module == "datetime":
                for alias in node.names:
                    if alias.name == "datetime":
                        self.classes.add(alias.asname or "datetime")

    def is_naive_clock(self, func: ast.expr) -> str | None:
        """Return the attribute name ('now'/'utcnow') for a naive clock ref."""
        if not isinstance(func, ast.Attribute) or func.attr not in _NAIVE_ATTRS:
            return None
        value = func.value
        # ``datetime.now`` where ``datetime`` is the class.
        if isinstance(value, ast.Name) and value.id in self.classes:
            return func.attr
        # ``datetime.datetime.now`` where the outer name is the module.
        if (
            isinstance(value, ast.Attribute)
            and value.attr == "datetime"
            and isinstance(value.value, ast.Name)
            and value.value.id in self.modules
        ):
            return func.attr
        return None


def _scan_source(rel_path: str, source: str) -> list[Offender]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    names = _DatetimeNames(tree)
    if not names.classes and not names.modules:
        return []

    lines = source.splitlines()
    allowed_lines = {
        i + 1 for i, line in enumerate(lines) if ALLOW_COMMENT in line
    }

    # Every attribute that is the callee of a call. Those are judged by the Call
    # node instead — so ``datetime.now(timezone.utc)`` is not also reported as a
    # bare reference, and ``datetime.now()`` is reported exactly once.
    callee_positions = {
        (node.func.lineno, node.func.col_offset)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }

    offenders: list[Offender] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            attr = names.is_naive_clock(node.func)
            # An explicit tz argument (positional or keyword) is the fix, not the
            # bug: datetime.now(timezone.utc) / datetime.now(tz=...).
            if attr is None or node.args or node.keywords:
                continue
            expr = f"datetime.{attr}()"
        elif isinstance(node, ast.Attribute):
            if (node.lineno, node.col_offset) in callee_positions:
                continue
            attr = names.is_naive_clock(node)
            if attr is None:
                continue
            expr = f"datetime.{attr} (bare reference, e.g. default_factory)"
        else:
            continue

        if node.lineno in allowed_lines:
            continue
        offenders.append(Offender(rel_path, node.lineno, expr))

    return sorted(offenders, key=lambda o: (o.line, o.expr))


def offenders() -> list[Offender]:
    found: list[Offender] = []
    for path in _iter_python_files(SCANNED_ROOTS):
        rel = _rel(path)
        if rel in SANCTIONED_FILES:
            continue
        found.extend(
            _scan_source(rel, path.read_text(encoding="utf-8", errors="ignore"))
        )
    return found


# ---------------------------------------------------------------------------
# Self-test: the rule must FIRE on the shapes it claims to catch.
# ---------------------------------------------------------------------------

_FIRES = (
    ("plain now", "from datetime import datetime\nx = datetime.now()\n"),
    ("utcnow", "from datetime import datetime\nx = datetime.utcnow()\n"),
    (
        "module form",
        "import datetime\nx = datetime.datetime.now()\n",
    ),
    (
        "aliased class",
        "from datetime import datetime as _dt\nx = _dt.now()\n",
    ),
    (
        "aliased module",
        "import datetime as dt\nx = dt.datetime.utcnow()\n",
    ),
    (
        "pydantic default_factory",
        "from datetime import datetime\nfrom pydantic import Field\n"
        "y = Field(default_factory=datetime.now)\n",
    ),
    (
        "dataclass default_factory",
        "from datetime import datetime\nfrom dataclasses import field\n"
        "y = field(default_factory=datetime.utcnow)\n",
    ),
    (
        "lambda wrapper",
        "from datetime import datetime\nf = lambda: datetime.now()\n",
    ),
    (
        "nested in f-string",
        "from datetime import datetime\ns = f\"{datetime.now().isoformat()}\"\n",
    ),
)

_PASSES = (
    (
        "aware utc",
        "from datetime import datetime, timezone\nx = datetime.now(timezone.utc)\n",
    ),
    (
        "aware keyword",
        "from datetime import datetime, timezone\nx = datetime.now(tz=timezone.utc)\n",
    ),
    (
        "zoneinfo",
        "from datetime import datetime\nfrom zoneinfo import ZoneInfo\n"
        "x = datetime.now(ZoneInfo('UTC'))\n",
    ),
    (
        "sanctioned helper call",
        "from fichero_server.core.timeutil import utc_now\nx = utc_now()\n",
    ),
    (
        "unrelated now attribute",
        "from datetime import datetime\nclass C:\n    now = 1\nx = C.now\n",
    ),
    (
        "naive form only in a comment",
        "from datetime import datetime\n# do not use datetime.now() here\nx = 1\n",
    ),
    (
        "naive form only in a docstring",
        'from datetime import datetime\n"""Never call datetime.utcnow()."""\nx = 1\n',
    ),
    (
        "explicit allow comment",
        "from datetime import datetime\n"
        f"x = datetime.now()  # {ALLOW_COMMENT}\n",
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
        "fichero-server/src/fichero_server/x.py",
        "from datetime import datetime\n\n\nv = datetime.now()\n",
    )
    assert [f.key for f in found] == ["fichero-server/src/fichero_server/x.py:4"], found


def main(argv: list[str]) -> int:
    if "--help" in argv or "-h" in argv:
        print(__doc__)
        return 0

    _self_test()
    if "--self-test" in argv:
        print("check_naive_datetimes self-test: OK")
        return 0

    found = offenders()

    if "--list" in argv:
        for offender in found:
            tag = "KNOWN" if offender.key in KNOWN_VIOLATIONS else "OFFENDER"
            print(f"[{tag}] {offender}")
        print()

    unexpected = [o for o in found if o.key not in KNOWN_VIOLATIONS]
    found_keys = {o.key for o in found}
    stale = sorted(k for k in KNOWN_VIOLATIONS if k not in found_keys)

    # #4487 scan floor: 438 files on 2026-08-02, computed on every path —
    # a violation run proves the scan lived; a clean run must prove it too.
    scanned = sum(1 for _ in _iter_python_files(SCANNED_ROOTS))
    require_scan_floor(scanned, 219, "Python files (438 on 2026-08-02)")

    if not unexpected and not stale:
        print(f"check_naive_datetimes: OK ({scanned} files, 0 naive clock reads)")
        return 0

    if unexpected:
        print("Naive datetime clock reads (use fichero_server.core.timeutil.utc_now):")
        for offender in unexpected:
            print(f"  {offender}")
        print()
        print("Fix: datetime.now() / datetime.utcnow() -> utc_now()")
        print("     Field(default_factory=datetime.now) -> default_factory=utc_now")
        print(f"     deliberate exception: trailing '# {ALLOW_COMMENT}'")

    if stale:
        print("Stale KNOWN_VIOLATIONS entries (fixed — delete them):")
        for key in stale:
            print(f"  {key}")

    return 1


def _require_scan_roots_4382(*roots):
    """#4382: a guardrail must know when it has gone blind, and say so.

    A missing scan root means "I could not check" (exit 2) -- never a silent
    exit 0. Distinct from exit 1 ("I checked and found violations"), so a
    moved or renamed directory can never disable this guardrail while the
    gate stays green.
    """
    import sys as _sys

    flat = []
    for root in roots:
        flat.extend(root if isinstance(root, (tuple, list)) else [root])
    missing = [str(r) for r in flat if not r.exists()]
    if missing:
        print(
            f"{__file__.rsplit('/', 1)[-1]}: BLIND -- scan root(s) missing: "
            + ", ".join(missing)
            + " (the tree moved; update this guardrail's paths)",
            file=_sys.stderr,
        )
        _sys.exit(2)


if __name__ == "__main__":
    _require_scan_roots_4382(SCANNED_ROOTS)
    sys.exit(main(sys.argv[1:]))
