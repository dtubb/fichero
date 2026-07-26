"""
DatabaseManager — connection pool for multi-library Fichero packages.

Each .fichero package directory gets its own Database instance.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import TYPE_CHECKING

from fichero.api.change_stream import emit_change
from fichero.db.library_paths import nfc_path

if TYPE_CHECKING:
    from fichero.db import Database

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Manages Database instances for package documents — ONE per package,
    shared across all threads (#2508).

    Each .fichero package contains its own database files:
    - MyLibrary.fichero/fichero.duckdb
    - MyLibrary.fichero/lance/

    A DuckDB ``Connection`` is not safe for *concurrent* use, but it IS safe
    when serialized by a lock. The manager keeps exactly one ``Database`` (one
    connection, one ``RLock``) per package; ``Database`` already wraps every
    typed read/write in ``with self._lock``, so a single shared instance makes
    that serialization globally effective and read-after-write deterministic
    across threads. Previously the pool was keyed by ``(package, thread_ident)``
    — each thread got its own connection+lock, so the locking never serialized
    across threads and cross-thread correctness rode on DuckDB MVCC alone (the
    root of #2430 per-page loss and #2462 phantom 404s).
    """

    def __init__(self):
        # Key: package_str -> Database. ONE shared connection per package across
        # all threads (#2508); Database._lock then serializes every access
        # globally. NEVER re-introduce a thread_ident in this key — that is the
        # exact hazard #2508 removed (see test_single_connection_guardrail).
        self._databases: dict[str, Database] = {}
        self._lock = threading.Lock()
        logger.info("DatabaseManager initialized")

    def get_database(self, package_path: str | Path) -> "Database":
        """Get or create the one shared Database instance for a package.

        The same instance (one DuckDB connection + one RLock) is returned on
        every thread (#2508); all access serializes on that lock.

        Args:
            package_path: Path to the .fichero package directory
                         (e.g., /Users/name/Documents/MyLibrary.fichero)

        Returns:
            The single shared Database instance for this package.
        """
        from fichero.db import Database
        from fichero.db.migrations.schema import (
            migrate_activity_tables,
            migrate_checkpoint_tables,
            migrate_provider_refs_table,
            migrate_saved_search_table,
            migrate_workflow_table,
        )
        from fichero.db.library_bootstrap import ensure_inbox_folder
        from fichero.db.paths import is_global_library_package
        from fichero.workflows.default_workflows import (
            prune_default_workflows,
            seed_default_workflows,
        )

        package_path = Path(nfc_path(package_path))
        package_str = str(package_path)
        cache_key = package_str

        with self._lock:
            if cache_key not in self._databases:
                db_path = package_path / "fichero.duckdb"
                logger.info(
                    f"Creating shared database connection for package: {package_str}"
                )

                db = Database(path=db_path)
                try:
                    migrate_workflow_table(db.conn)
                    migrate_saved_search_table(db.conn)
                    migrate_provider_refs_table(db.conn)
                    migrate_activity_tables(db.conn)
                    migrate_checkpoint_tables(db.conn)

                    # Seed default workflow presets (Transcribe, Catalogue) into
                    # the GLOBAL library only (#4102) — they're app-level presets,
                    # and a per-library copy made the same "Default Workflows"
                    # folder appear under every library in the sidebar. A library
                    # keeps its own custom workflows; it just doesn't get the
                    # shipped ones. Seeding is idempotent by workflow name, so a
                    # user who deleted a preset doesn't get it back. Non-global
                    # libraries seeded before this rule are healed by the prune.
                    # Tests set FICHERO_SKIP_DEFAULT_WORKFLOWS=1 so fixtures that
                    # assert on "empty library" keep working without per-test cleanup.
                    import os

                    if os.environ.get("FICHERO_SKIP_DEFAULT_WORKFLOWS") != "1":
                        if is_global_library_package(package_path):
                            seeded = seed_default_workflows(db)
                            if seeded:
                                logger.info(f"Seeded {seeded} default workflow preset(s)")
                        else:
                            prune_default_workflows(db)

                    ensure_inbox_folder(db)
                except Exception as exc:
                    db.close()
                    logger.exception("Failed to initialize library database: %s", package_str)
                    raise RuntimeError(
                        f"Failed to initialize library database: {package_str}"
                    ) from exc

                self._databases[cache_key] = db
                logger.info(f"Database connection created: {db_path}")
                emit_change(
                    package_str,
                    type="library.opened",
                    actor="system",
                    metadata={
                        "library_name": package_path.name,
                        "source": "db_manager",
                    },
                )

            return self._databases[cache_key]

    def close_database(self, package_path: str | Path):
        """Close the shared connection for a package."""
        package_str = str(Path(nfc_path(package_path)).expanduser().resolve())

        with self._lock:
            keys = [k for k in self._databases if k == package_str]
            for key in keys:
                self._databases.pop(key).close()
                logger.info(f"Closed database connection: {package_str}")

    def quiesce_database(
        self,
        package_path: str | Path,
        *,
        checkpoint: bool = True,
        close: bool = False,
        timeout: float | None = 120.0,
    ) -> None:
        """Checkpoint and optionally close a package DB.

        This is the safety seam for filesystem-level snapshot/restore work. All
        writes serialize on the package's single shared connection lock (#2508),
        so taking that lock to CHECKPOINT is sufficient to quiesce managed
        writes; independent direct DuckDB connections outside the manager remain
        outside this lock's scope.
        """
        package_str = str(Path(nfc_path(package_path)))

        with self._lock:
            keys = [k for k in self._databases if k == package_str]

            if checkpoint:
                for key in keys:
                    db = self._databases[key]
                    with db._lock:
                        db.conn.execute("CHECKPOINT")
                    logger.info("Checkpointed database: %s", package_str)

            if close:
                for key in keys:
                    self._databases.pop(key).close()
                    logger.info("Closed database connection: %s", package_str)

    def close_current_thread(self) -> None:
        """No-op under the single-connection model (#2508).

        Previously each thread owned its own connection and a workflow worker
        closed it in its ``finally`` to avoid leaking. Now there is ONE shared
        connection per package owned by the manager — a worker thread must NOT
        close it (the event loop and every other thread share it). Connection
        teardown is owned by ``close_database`` / ``close_all`` /
        ``quiesce_database``. Kept as a no-op so existing ``finally`` callers
        (e.g. task_workers) need no change.
        """
        return

    @property
    def active_count(self) -> int:
        """Number of packages with an open shared connection."""
        return len(self._databases)

    def open_library_paths(self) -> list[str]:
        """Return a stable snapshot of package paths with live connections."""
        with self._lock:
            return sorted(self._databases)

    def close_all(self):
        """Close every package's shared connection."""
        with self._lock:
            for cache_key, db in list(self._databases.items()):
                db.close()
                logger.info(f"Closed database: {cache_key}")
            self._databases.clear()
            logger.info("All database connections closed")


# Global singleton
db_manager = DatabaseManager()
