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

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Manages multiple Database instances for package documents.

    Each .fichero package contains its own database files:
    - MyLibrary.fichero/fichero.duckdb
    - MyLibrary.fichero/lance/

    The manager maintains a pool of open Database connections.
    """

    def __init__(self):
        self._databases: dict[str, Database] = {}
        self._lock = threading.Lock()
        logger.info("DatabaseManager initialized")

    def get_database(self, package_path: str | Path) -> "Database":
        """Get or create Database instance for a package.

        Args:
            package_path: Path to the .fichero package directory
                         (e.g., /Users/name/Documents/MyLibrary.fichero)

        Returns:
            Database instance for this package
        """
        from fichero.db import Database
        from fichero.db_migrations import (
            migrate_activity_tables,
            migrate_checkpoint_tables,
            migrate_provider_refs_table,
            migrate_saved_search_table,
            migrate_workflow_table,
        )
        from fichero.workflows.default_workflows import seed_default_workflows

        package_path = Path(package_path)
        package_str = str(package_path)

        with self._lock:
            if package_str not in self._databases:
                db_path = package_path / "fichero.duckdb"
                logger.info(f"Creating database connection for package: {package_str}")

                db = Database(path=db_path)

                migrate_workflow_table(db.conn)
                migrate_saved_search_table(db.conn)
                migrate_provider_refs_table(db.conn)
                migrate_activity_tables(db.conn)
                migrate_checkpoint_tables(db.conn)

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

                self._databases[package_str] = db
                logger.info(f"Database connection created: {db_path}")

            return self._databases[package_str]

    def close_database(self, package_path: str | Path):
        """Close database connection for a package."""
        package_str = str(Path(package_path))

        with self._lock:
            if package_str in self._databases:
                db = self._databases[package_str]
                db.conn.close()
                del self._databases[package_str]
                logger.info(f"Closed database connection: {package_str}")

    @property
    def active_count(self) -> int:
        """Return the number of currently open database connections."""
        return len(self._databases)

    def close_all(self):
        """Close all database connections."""
        with self._lock:
            for package_path, db in list(self._databases.items()):
                db.conn.close()
                logger.info(f"Closed database: {package_path}")
            self._databases.clear()
            logger.info("All database connections closed")


# Global singleton
db_manager = DatabaseManager()
