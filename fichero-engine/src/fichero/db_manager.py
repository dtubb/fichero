"""
DatabaseManager — connection pool for multi-library Fichero packages.

Each .fichero package directory gets its own Database instance.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fichero.db import Database
    from fichero.db_writer import DBWriter

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Manages Database instances for package documents — one per
    (package, thread).

    Each .fichero package contains its own database files:
    - MyLibrary.fichero/fichero.duckdb
    - MyLibrary.fichero/lance/

    A DuckDB ``Connection`` is not safe to share across threads. Since
    workflow execution now runs on a dedicated worker thread (#1000),
    the manager keys its connection pool by ``(package_path, thread_id)``
    so the API thread and a workflow worker thread each get their own
    connection to the same file. DuckDB allows multiple in-process
    connections to one database and serialises writes internally, so
    cross-thread visibility still works — the threads just don't share
    a ``Connection`` object.
    """

    def __init__(self):
        # Key: (package_str, thread_ident) -> Database
        self._databases: dict[tuple[str, int], Database] = {}
        # Key: (package_str, thread_ident) -> DBWriter (lazily created;
        # see get_db_writer). Single-writer queue for #1000 Phase 2.
        self._db_writers: dict[tuple[str, int], "DBWriter"] = {}
        self._lock = threading.Lock()
        logger.info("DatabaseManager initialized")

    def get_database(self, package_path: str | Path) -> "Database":
        """Get or create the Database instance for a package, scoped to
        the calling thread.

        Args:
            package_path: Path to the .fichero package directory
                         (e.g., /Users/name/Documents/MyLibrary.fichero)

        Returns:
            Database instance for this package, owned by the current thread.
        """
        from fichero.db import Database
        from fichero.db_migrations import (
            migrate_activity_tables,
            migrate_checkpoint_tables,
            migrate_knowledge_claims_provider_model,
            migrate_provider_refs_table,
            migrate_saved_search_table,
            migrate_workflow_table,
        )
        from fichero.workflows.default_workflows import seed_default_workflows

        package_path = Path(package_path)
        package_str = str(package_path)
        cache_key = (package_str, threading.get_ident())

        with self._lock:
            if cache_key not in self._databases:
                db_path = package_path / "fichero.duckdb"
                logger.info(
                    f"Creating database connection for package: {package_str} "
                    f"(thread {cache_key[1]})"
                )

                db = Database(path=db_path)

                migrate_workflow_table(db.conn)
                migrate_saved_search_table(db.conn)
                migrate_provider_refs_table(db.conn)
                migrate_activity_tables(db.conn)
                migrate_checkpoint_tables(db.conn)
                migrate_knowledge_claims_provider_model(db.conn)

                # Seed default workflow presets (Transcribe, Catalogue). Idempotent
                # by workflow name — a user who deleted a preset doesn't get it back.
                # Tests set FICHERO_SKIP_DEFAULT_WORKFLOWS=1 so fixtures that assert
                # on "empty library" keep working without per-test cleanup.
                import os

                if os.environ.get("FICHERO_SKIP_DEFAULT_WORKFLOWS") != "1":
                    try:
                        seeded = seed_default_workflows(db)
                        if seeded:
                            logger.info(f"Seeded {seeded} default workflow preset(s)")
                    except Exception as exc:
                        logger.warning(f"Default workflow seeding skipped: {exc}")

                self._databases[cache_key] = db
                logger.info(f"Database connection created: {db_path}")

            return self._databases[cache_key]

    def get_db_writer(self, package_path: str | Path) -> "DBWriter":
        """Get or create the single-writer queue for a package, scoped
        to the calling thread (#1000 Phase 2).

        Lazily created on first use and bound to this thread's
        ``Database`` connection — so the writer owns that connection's
        write path exclusively. Lifecycle is tied to the connection:
        ``close_database`` / ``close_all`` / ``close_current_thread``
        stop it.
        """
        from fichero.db_writer import DBWriter

        package_path = Path(package_path)
        package_str = str(package_path)
        cache_key = (package_str, threading.get_ident())

        # get_database is itself locked; call it before taking the lock.
        db = self.get_database(package_path)
        with self._lock:
            if cache_key not in self._db_writers:
                writer = DBWriter(db, name=f"db-writer-{cache_key[1]}")
                writer.start()
                self._db_writers[cache_key] = writer
                logger.info(
                    f"DBWriter created: {package_str} (thread {cache_key[1]})"
                )
            return self._db_writers[cache_key]

    def _stop_writers(self, keys: list[tuple[str, int]]) -> None:
        """Stop and drop the DBWriters for the given cache keys.
        Caller must hold ``self._lock``."""
        for key in keys:
            writer = self._db_writers.pop(key, None)
            if writer is not None:
                writer.stop()

    def close_database(self, package_path: str | Path):
        """Close every thread's connection (and writer) for a package."""
        package_str = str(Path(package_path))

        with self._lock:
            keys = [k for k in self._databases if k[0] == package_str]
            self._stop_writers(
                [k for k in self._db_writers if k[0] == package_str]
            )
            for key in keys:
                self._databases.pop(key).conn.close()
                logger.info(
                    f"Closed database connection: {package_str} (thread {key[1]})"
                )

    def close_current_thread(self) -> None:
        """Close this thread's connection + writer for every package.

        Called by the workflow worker thread in its ``finally`` so a
        finished run doesn't leak its DuckDB connection / writer thread
        (#1000). The API thread's connections are untouched.
        """
        tid = threading.get_ident()
        with self._lock:
            self._stop_writers([k for k in self._db_writers if k[1] == tid])
            for key in [k for k in self._databases if k[1] == tid]:
                self._databases.pop(key).conn.close()
                logger.debug(
                    f"Closed database connection: {key[0]} (thread {tid})"
                )

    @property
    def active_count(self) -> int:
        """Number of distinct packages with at least one open connection."""
        return len({key[0] for key in self._databases})

    def close_all(self):
        """Close all database connections + writers across every thread."""
        with self._lock:
            self._stop_writers(list(self._db_writers))
            for cache_key, db in list(self._databases.items()):
                db.conn.close()
                logger.info(
                    f"Closed database: {cache_key[0]} (thread {cache_key[1]})"
                )
            self._databases.clear()
            logger.info("All database connections closed")


# Global singleton
db_manager = DatabaseManager()
