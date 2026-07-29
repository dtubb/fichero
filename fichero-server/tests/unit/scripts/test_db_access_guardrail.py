"""Architecture guardrail: raw DuckDB/SQL access stays in the DB layer.

Rule (#1876)
------------
Raw DuckDB connections and hand-written SQL must live ONLY in the persistence
layer (``db.py`` and its siblings, behind typed methods that return Pydantic
models). Routes, services, and business logic must call those typed methods --
they must NEVER touch a raw DuckDB connection or embed SQL directly.

Why this matters:
  * ``db.py`` is the single choke point where the schema, parameter binding,
    and Pydantic (de)serialization are guaranteed. Reaching past it (e.g.
    ``db.conn.execute("SELECT ...")`` inside a route) silently bypasses typed
    models, breaks the OpenAPI contract, and scatters SQL that nobody can audit
    or migrate safely.
  * If you need data a route can't reach, add a typed method to ``db.py`` --
    do NOT open ``.conn`` in the route.  See ``fichero/db.py``.

This test walks ``fichero-server/src/fichero_server/**/*.py`` and (via AST) flags any
file outside the persistence-layer allowlist that references a raw connection
(``.conn``, ``duckdb.connect``, ``.cursor()``, ``self._execute(...)``) or embeds
a raw SQL string literal (``SELECT ... FROM``, ``INSERT INTO``, ``UPDATE ... SET``,
``DELETE FROM``).

KNOWN_VIOLATIONS captures the pre-existing debt that predates this guard so the
suite is green today while the debt stays visible. New code must NOT add to it;
the goal is to drive it to empty.  See #1876 for the follow-up issues.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

# fichero-server/src/fichero_server
SRC_ROOT = Path(__file__).resolve().parents[3] / "src" / "fichero_server"

# --------------------------------------------------------------------------
# Allowlist: the persistence layer is *permitted* to contain raw SQL/DuckDB.
# Paths are POSIX-relative to SRC_ROOT.  A path is allowed if it matches an
# entry exactly, or if any path segment is "migrations" (migration scripts).
# --------------------------------------------------------------------------
ALLOWLIST: frozenset[str] = frozenset(
    {
        # Core DB layer
        "db/__init__.py",
        "db/embeddings.py",
        "db/migrations/schema.py",
        "db/manager.py",
        "db/app.py",
        "db/migrations/runner.py",
        "api/change_stream.py",
        # Backup / restore handles raw connections to snapshot the .duckdb file.
        "db/storage_snapshots.py",
        # Workflow-subsystem persistence stores (each is the DB layer for its
        # own concern: checkpointing, scheduling, caching, activity, tasks,
        # and actions). Consolidating these behind db.py is future work (#1876).
        # BatchManager similarly owns its batch tables and persistence contract.
        "execution/batch.py",
        "workflows/action_store.py",
        "workflows/cache.py",
        "workflows/checkpointer.py",
        "workflows/activity_store.py",
        "workflows/batch.py",
        "workflows/file_watcher.py",
        "workflows/scheduler.py",
        "workflows/tasks.py",
    }
)

# --------------------------------------------------------------------------
# Pre-existing debt: routes / business logic that reach into a raw connection.
# These predate the guardrail (#1876). Do NOT add to this list -- add a typed
# method to db.py instead. Drive this set to empty.
# --------------------------------------------------------------------------
KNOWN_VIOLATIONS: frozenset[str] = frozenset()

# A string literal counts as raw SQL only if it has real SQL *structure*; this
# avoids flagging SPARQL queries ("SELECT ?p WHERE { ... }") and HTTP verbs.
_SQL_PATTERNS = (
    re.compile(r"^\s*SELECT\b.*\bFROM\b", re.IGNORECASE | re.DOTALL),
    re.compile(r"^\s*INSERT\s+INTO\b", re.IGNORECASE),
    re.compile(r"^\s*UPDATE\b.*\bSET\b", re.IGNORECASE | re.DOTALL),
    re.compile(r"^\s*DELETE\s+FROM\b", re.IGNORECASE),
)


def _looks_like_sql(value: str) -> bool:
    # SPARQL guard: SPARQL uses ?vars and "{ ... }" graph patterns; never SQL.
    if "{" in value or re.search(r"\?\w", value):
        return False
    return any(p.search(value) for p in _SQL_PATTERNS)


class _RawDbScanner(ast.NodeVisitor):
    """Collect raw-DB-access signals: (kind, lineno)."""

    def __init__(self) -> None:
        self.hits: list[tuple[str, int]] = []

    def visit_Attribute(self, node: ast.Attribute) -> None:
        # `.conn` / `.duck` raw DuckDB connection handles
        # (covers self.conn, db.conn, app_db.conn, db.duck.execute, ...)
        if node.attr in ("conn", "duck"):
            self.hits.append((f"raw .{node.attr} access", node.lineno))
        # `.cursor(`  -> attribute named cursor used as a call
        if node.attr == "cursor":
            self.hits.append((".cursor()", node.lineno))
        # `duckdb.connect(`
        if (
            node.attr == "connect"
            and isinstance(node.value, ast.Name)
            and node.value.id == "duckdb"
        ):
            self.hits.append(("duckdb.connect", node.lineno))
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        name = None
        if isinstance(func, ast.Attribute):
            name = func.attr
        elif isinstance(func, ast.Name):
            name = func.id
        if name == "_execute":
            self.hits.append(("_execute()", node.lineno))
        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> None:
        if isinstance(node.value, str) and _looks_like_sql(node.value):
            self.hits.append(("raw SQL string literal", node.lineno))
        self.generic_visit(node)


def _rel(path: Path) -> str:
    return path.relative_to(SRC_ROOT).as_posix()


def _is_allowlisted(rel: str) -> bool:
    if rel in ALLOWLIST:
        return True
    # anything under a `migrations/` directory
    return "migrations" in Path(rel).parts


def _scan_source_tree() -> dict[str, list[tuple[str, int]]]:
    """Return {relpath: [(kind, lineno), ...]} for every flagged non-allowlist file."""
    flagged: dict[str, list[tuple[str, int]]] = {}
    for path in sorted(SRC_ROOT.rglob("*.py")):
        rel = _rel(path)
        # Generated code (e.g. the OpenAPI CLI client under cli/generated/) is
        # not hand-written business logic — SQL-looking strings there are field
        # descriptions, not raw DB access. Skip any `generated/` directory.
        if "generated" in path.parts:
            continue
        if _is_allowlisted(rel):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):  # pragma: no cover - defensive
            continue
        scanner = _RawDbScanner()
        scanner.visit(tree)
        if scanner.hits:
            flagged[rel] = scanner.hits
    return flagged


_RULE_REMINDER = (
    "ARCHITECTURE RULE (#1876): raw DuckDB connections and SQL must live ONLY "
    "in the persistence layer (fichero/db.py and its siblings), behind typed "
    "methods that return Pydantic models. Routes/services/business-logic must "
    "call those typed methods -- never `.conn`/`.duck`, `.cursor()`, `duckdb.connect`, "
    "`_execute(...)`, or inline SQL. If a route needs data it can't reach, add "
    "a typed method to fichero/db.py."
)


def test_no_new_raw_db_access_outside_persistence_layer() -> None:
    flagged = _scan_source_tree()
    new_violations = {
        rel: hits for rel, hits in flagged.items() if rel not in KNOWN_VIOLATIONS
    }
    if new_violations:
        lines = [_RULE_REMINDER, "", "New raw-DB access detected:"]
        for rel in sorted(new_violations):
            for kind, lineno in new_violations[rel]:
                lines.append(f"  {rel}:{lineno}: {kind}")
        lines.append("")
        lines.append(
            "Move this SQL behind a typed method in fichero/db.py, or -- if this "
            "is genuinely persistence-layer code -- add the file to ALLOWLIST "
            "with a justifying comment."
        )
        pytest.fail("\n".join(lines))


def test_known_violations_list_is_not_stale() -> None:
    """Once a known violation is fixed, it must be removed from KNOWN_VIOLATIONS
    so the debt list stays honest and the guard re-arms for that file."""
    flagged = _scan_source_tree()
    stale = sorted(rel for rel in KNOWN_VIOLATIONS if rel not in flagged)
    assert not stale, (
        "These files are in KNOWN_VIOLATIONS but no longer access raw DB -- "
        "remove them so the guardrail re-arms:\n  " + "\n  ".join(stale)
    )


def test_allowlist_entries_exist() -> None:
    """Guard against typos / dead allowlist entries drifting from the tree."""
    missing = sorted(
        rel
        for rel in ALLOWLIST
        if "migrations" not in Path(rel).parts and not (SRC_ROOT / rel).exists()
    )
    assert not missing, f"ALLOWLIST references nonexistent files: {missing}"
