"""Permanent guardrail for the #2508 single-connection write model (Phase 4).

#2508 collapsed ``DatabaseManager`` to ONE shared DuckDB connection + ONE
``RLock`` per package. Two regressions would silently re-open the door to the
exact hazards #2508 closed (per-page artifact loss #2430, phantom 404s #2462,
cross-thread torn reads):

  1. Re-keying the ``DatabaseManager`` connection pool by
     ``threading.get_ident()`` — that hands each thread its own connection again,
     so the per-method ``with self._lock`` serialization becomes per-thread and
     never serializes across threads. (STATIC check.)

  2. A direct-SQL store or a route reaching past the locked seam to run raw SQL
     on a connection *attribute* (``X.conn.execute(...)`` / ``X.duck.execute(...)``)
     outside the persistence layer and the (now-shrunk) store allowlist. Under
     the single shared connection every such statement MUST go through the
     ``Database`` locked helpers (``db.execute`` / ``db.execute_fetchall`` /
     ``db.execute_fetchone``). (BYPASS check.)

Plus a RUNTIME check that ``get_database`` actually returns the one shared
instance across real threads.

This complements (does not duplicate) ``test_db_access_guardrail.py`` (#1876),
which guards the broader "no raw SQL outside the DB layer" rule. This file is
the narrow #2508 connection-topology guard.
"""

from __future__ import annotations

import ast
import threading
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

# fichero-server/src/fichero_server
SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "fichero"


# ===========================================================================
# 1. STATIC — the connection pool must never be keyed by thread identity.
# ===========================================================================
def _references_get_ident(tree: ast.AST) -> list[int]:
    """Return linenos of any ``get_ident`` reference (the #2508 hazard).

    Matches ``threading.get_ident``, ``get_ident``, and aliased imports —
    db_manager has no legitimate use for thread identity under the single
    shared connection, so ANY reference is a regression. No allowlist.
    """
    hits: list[int] = []

    class _V(ast.NodeVisitor):
        def visit_Attribute(self, node: ast.Attribute) -> None:
            if node.attr == "get_ident":
                hits.append(node.lineno)
            self.generic_visit(node)

        def visit_Name(self, node: ast.Name) -> None:
            if node.id == "get_ident":
                hits.append(node.lineno)
            self.generic_visit(node)

    _V().visit(tree)
    return hits


def test_db_manager_pool_not_keyed_by_thread_ident() -> None:
    """db_manager.py must NOT reference ``get_ident`` anywhere — re-introducing a
    per-thread connection key is the exact #2508 hazard."""
    db_manager_py = SRC_ROOT / "db" / "manager.py"
    tree = ast.parse(db_manager_py.read_text(encoding="utf-8"))
    hits = _references_get_ident(tree)
    assert not hits, (
        "db_manager.py references threading.get_ident() at lines "
        f"{hits} — the #2508 single-connection pool must be keyed by package "
        "ONLY, never by thread identity. A per-thread key gives each thread its "
        "own DuckDB connection, so Database._lock no longer serializes across "
        "threads (root of #2430 per-page loss / #2462 phantom 404s)."
    )


# ===========================================================================
# 2. RUNTIME — one shared Database instance per package across all threads.
# ===========================================================================
def test_get_database_is_one_shared_instance_across_threads(tmp_path, monkeypatch) -> None:
    """K real threads opening the same package get the SAME Database object, and
    db_manager holds exactly ONE pool entry for that package."""
    monkeypatch.setenv("FICHERO_SKIP_DEFAULT_WORKFLOWS", "1")
    from fichero_server.db.manager import DatabaseManager

    manager = DatabaseManager()
    lib = tmp_path / "Guardrail.fichero"
    lib.mkdir(parents=True, exist_ok=True)
    package = str(lib)

    try:
        main = manager.get_database(package)
        results: dict[int, object] = {}

        def worker() -> None:
            results[threading.get_ident()] = manager.get_database(package)

        with ThreadPoolExecutor(max_workers=8) as ex:
            for _ in range(8):
                ex.submit(worker)

        assert results, "no worker threads ran"
        for db in results.values():
            assert db is main, "get_database must return the same instance on every thread"
            assert db.conn is main.conn, "all threads must share one DuckDB connection"

        # Exactly one pool entry for the package (no per-thread fan-out).
        package_entries = [k for k in manager._databases if k == package]
        assert len(package_entries) == 1, (
            f"expected exactly 1 pool entry for {package}, found "
            f"{len(package_entries)}: {package_entries}"
        )
        assert manager.active_count == 1
    finally:
        manager.close_all()


def test_get_database_normalizes_unicode_equivalent_package_keys(tmp_path, monkeypatch) -> None:
    """NFD/NFC spellings of one package path must hit one shared cache entry."""
    monkeypatch.setenv("FICHERO_SKIP_DEFAULT_WORKFLOWS", "1")
    from fichero_server.db.manager import DatabaseManager

    manager = DatabaseManager()
    lib = tmp_path / unicodedata.normalize("NFC", "Chocó.fichero")
    lib.mkdir(parents=True, exist_ok=True)
    nfd_path = unicodedata.normalize("NFD", str(lib))
    nfc_path = unicodedata.normalize("NFC", str(lib))

    try:
        first = manager.get_database(nfd_path)
        second = manager.get_database(nfc_path)
        assert first is second
        assert list(manager._databases) == [nfc_path]
    finally:
        manager.close_all()


# ===========================================================================
# 3. BYPASS — no raw ``.conn.execute`` / ``.duck.execute`` outside the seam.
# ===========================================================================
# Files permitted to execute raw SQL on a connection *attribute*
# (``X.conn.execute`` / ``X.duck.execute``). Paths are POSIX-relative to
# SRC_ROOT. The persistence layer owns the typed/locked seam; the two workflow
# stores below each own a SEPARATE raw duckdb connection (NOT the package's
# managed shared one — documented inline with a ``ponytail:`` note), so they are
# outside the Database._lock seam by design.
#
# NOTE the action store is intentionally ABSENT: #2508 Phase 3b migrated it off
# ``db.duck.execute`` onto the locked helpers, so it carries zero connection-
# attribute SQL debt. Folding cache.py / checkpointer.py onto the shared
# Database would empty this set entirely.
_CONN_EXECUTE_ALLOWLIST: frozenset[str] = frozenset(
    {
        # Persistence layer — defines the seam.
        "db/__init__.py",
        "db/manager.py",
        "db/migrations/schema.py",
        "db/embeddings.py",
        "db/app.py",
        # Workflow stores that own a separate raw connection (lead-review debt).
        "workflows/cache.py",
        "workflows/checkpointer.py",
    }
)

_EXEC_METHODS = {"execute", "executemany", "executescript"}
_CONN_ATTRS = {"conn", "duck"}


def _conn_attr_execute_hits(tree: ast.AST) -> list[int]:
    """Linenos of calls shaped ``<expr>.conn.execute(...)`` / ``.duck.execute(...)``.

    Only matches when the connection is reached via an *attribute* named
    ``conn``/``duck`` (e.g. ``self.conn.execute``, ``db.duck.execute``,
    ``self.db.duck.execute``). A bare local ``conn.execute`` where ``conn`` is a
    freshly-opened, per-operation ``duckdb.connect`` handle (activity_store /
    scheduler / tasks pattern) is NOT matched — that is a connection-per-op
    handle, not a shared connection touched past the seam.
    """
    hits: list[int] = []

    class _V(ast.NodeVisitor):
        def visit_Call(self, node: ast.Call) -> None:
            func = node.func
            if (
                isinstance(func, ast.Attribute)
                and func.attr in _EXEC_METHODS
                and isinstance(func.value, ast.Attribute)
                and func.value.attr in _CONN_ATTRS
            ):
                hits.append(node.lineno)
            self.generic_visit(node)

    _V().visit(tree)
    return hits


def _scan_for_conn_attr_execute() -> dict[str, list[int]]:
    flagged: dict[str, list[int]] = {}
    for path in sorted(SRC_ROOT.rglob("*.py")):
        rel = path.relative_to(SRC_ROOT).as_posix()
        if "generated" in path.parts:
            continue
        if rel in _CONN_EXECUTE_ALLOWLIST:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):  # pragma: no cover - defensive
            continue
        hits = _conn_attr_execute_hits(tree)
        if hits:
            flagged[rel] = hits
    return flagged


def test_no_raw_conn_attr_execute_outside_seam() -> None:
    """No file outside the DB layer + store allowlist may run raw SQL on a
    ``.conn``/``.duck`` connection attribute. Route every such statement through
    the Database locked helpers (db.execute / db.execute_fetchall /
    db.execute_fetchone) so it serializes on the one shared connection (#2508)."""
    flagged = _scan_for_conn_attr_execute()
    if flagged:
        lines = [
            "Raw connection-attribute SQL found outside the #2508 locked seam:",
            "",
        ]
        for rel in sorted(flagged):
            for lineno in flagged[rel]:
                lines.append(f"  {rel}:{lineno}: X.conn/.duck.execute(...)")
        lines += [
            "",
            "Under the single shared connection (#2508) this is a data race. Use "
            "db.execute / db.execute_fetchall / db.execute_fetchone (which serialize "
            "on Database._lock), or — if this is a genuinely separate, self-locked "
            "raw connection — add the file to _CONN_EXECUTE_ALLOWLIST with a "
            "justifying ponytail note.",
        ]
        pytest.fail("\n".join(lines))
    assert flagged == {}


def test_conn_execute_allowlist_has_no_dead_entries() -> None:
    """Every allowlisted file must exist — keep the list honest as code moves."""
    missing = sorted(
        rel for rel in _CONN_EXECUTE_ALLOWLIST if not (SRC_ROOT / rel).exists()
    )
    assert not missing, f"_CONN_EXECUTE_ALLOWLIST references nonexistent files: {missing}"
