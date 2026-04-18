"""
DuckDB schema migrations for Fichero.

Each function takes an open DuckDB connection and is idempotent.
Called by Database.__init__ and DatabaseManager.get_database.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def migrate_workflow_table(conn) -> None:
    """Migrate workflows table to new schema if needed."""
    from fichero.errors import ErrorCategory, handle_error

    try:
        table_exists = (
            conn.execute("""
            SELECT COUNT(*) FROM information_schema.tables
            WHERE table_name = 'workflows'
        """).fetchone()[0]
            > 0
        )

        if not table_exists:
            logger.debug("Workflows table does not exist, skipping migration")
            return

        result = conn.execute("PRAGMA table_info('workflows')").fetchall()
        columns = [row[1] for row in result]

        if "steps" in columns and "format" not in columns:
            logger.info("Migrating workflows table to new schema...")

            conn.execute("""
                ALTER TABLE workflows
                ADD COLUMN format VARCHAR DEFAULT 'steps'
            """)
            conn.execute("""
                ALTER TABLE workflows
                ADD COLUMN nodes JSON DEFAULT []
            """)
            conn.execute("""
                ALTER TABLE workflows
                ADD COLUMN edges JSON DEFAULT []
            """)
            conn.execute("""
                ALTER TABLE workflows
                ADD COLUMN folder_path VARCHAR DEFAULT '/'
            """)
            conn.execute("""
                ALTER TABLE workflows
                ADD COLUMN sort_order INTEGER DEFAULT 0
            """)
            conn.execute("""
                ALTER TABLE workflows
                ADD COLUMN is_template BOOLEAN DEFAULT FALSE
            """)
            conn.execute("""
                ALTER TABLE workflows
                ADD COLUMN tags JSON DEFAULT []
            """)
            conn.execute("""
                ALTER TABLE workflows
                ADD COLUMN provider VARCHAR DEFAULT ''
            """)
            conn.execute("""
                ALTER TABLE workflows
                ADD COLUMN model VARCHAR DEFAULT ''
            """)
            conn.execute("""
                UPDATE workflows
                SET format = 'steps'
                WHERE format IS NULL OR format = ''
            """)

            logger.info("Workflows table migration completed")

    except Exception as e:
        error = handle_error(
            e,
            default_message="Workflow table migration failed",
            category=ErrorCategory.DATABASE,
            context={"operation": "workflow_table_migration"},
        )
        logger.warning("Migration failed: %s", error.message)
        raise


def migrate_document_table(conn) -> None:
    """Migrate documents table to add the sort_order column.

    Older installations (pre-0.0.2 reorder work, pre-`#607`) created the
    documents table without `sort_order`. The Pydantic Document model
    now includes `sort_order: int = 0`, so every `INSERT OR REPLACE INTO
    documents` fails with a DuckDB Binder Error ("does not have a column
    with name sort_order"). Seen in Daniel's 2026-04-18 repro:

        _duckdb.BinderException: Binder Error: Table "documents" does
        not have a column with name "sort_order". Did you mean: "id"

    Fix: ALTER TABLE the existing documents table to add the column
    with default 0. Idempotent — skips if the column already exists,
    or if the table hasn't been created yet (first-launch path uses
    `_ensure_table` which picks up the current schema automatically).
    """
    try:
        table_exists = (
            conn.execute("""
            SELECT COUNT(*) FROM information_schema.tables
            WHERE table_name = 'documents'
        """).fetchone()[0]
            > 0
        )

        if not table_exists:
            logger.debug("Documents table does not exist, skipping migration")
            return

        result = conn.execute("PRAGMA table_info('documents')").fetchall()
        columns = {row[1]: row for row in result}

        if "sort_order" not in columns:
            logger.info("Migrating documents table: adding sort_order column...")
            conn.execute("""
                ALTER TABLE documents
                ADD COLUMN sort_order INTEGER DEFAULT 0
            """)

        logger.info("Documents table migration completed")

    except Exception as e:
        logger.warning(f"Documents migration check failed: {e}")


def migrate_saved_search_table(conn) -> None:
    """Migrate saved_searches table to add missing columns."""
    try:
        table_exists = (
            conn.execute("""
            SELECT COUNT(*) FROM information_schema.tables
            WHERE table_name = 'saved_searches'
        """).fetchone()[0]
            > 0
        )

        if not table_exists:
            logger.debug("Saved searches table does not exist, skipping migration")
            return

        result = conn.execute("PRAGMA table_info('saved_searches')").fetchall()
        columns = {row[1]: row for row in result}

        if "folder_path" not in columns:
            logger.info("Migrating saved_searches table: adding folder_path column...")
            conn.execute("""
                ALTER TABLE saved_searches
                ADD COLUMN folder_path VARCHAR DEFAULT '/'
            """)

        if "sort_order" not in columns:
            logger.info("Migrating saved_searches table: adding sort_order column...")
            conn.execute("""
                ALTER TABLE saved_searches
                ADD COLUMN sort_order INTEGER DEFAULT 0
            """)

        if "sort_direction" not in columns:
            logger.info(
                "Migrating saved_searches table: adding sort_direction column..."
            )
            conn.execute("""
                ALTER TABLE saved_searches
                ADD COLUMN sort_direction VARCHAR DEFAULT 'desc'
            """)

        logger.info("Saved searches table migration completed")

    except Exception as e:
        logger.warning(f"Saved searches migration check failed: {e}")


def migrate_provider_refs_table(conn) -> None:
    """Create provider_refs table if it doesn't exist.

    This table tracks which app-wide providers a library references.
    Actual provider config is stored in app.duckdb.
    """
    try:
        table_exists = (
            conn.execute("""
            SELECT COUNT(*) FROM information_schema.tables
            WHERE table_name = 'provider_refs'
        """).fetchone()[0]
            > 0
        )

        if table_exists:
            logger.debug("provider_refs table already exists")
            return

        logger.info("Creating provider_refs table...")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS provider_refs (
                id VARCHAR PRIMARY KEY,
                provider_id VARCHAR NOT NULL,
                enabled BOOLEAN DEFAULT TRUE,
                sort_order INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_provider_refs_provider
            ON provider_refs(provider_id)
        """)

        logger.info("provider_refs table created successfully")

    except Exception as e:
        logger.warning(f"provider_refs table creation failed: {e}")


def migrate_activity_tables(conn) -> None:
    """Ensure activity tracking tables exist.

    Creates the activities table for storing workflow execution events.
    This enables the Activity sidebar to show historical data.
    """
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS activities (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                level TEXT NOT NULL,
                timestamp TIMESTAMP NOT NULL,
                message TEXT NOT NULL,
                workflow_id TEXT,
                batch_id TEXT,
                thread_id TEXT,
                node_id TEXT,
                metadata JSON,
                duration_ms FLOAT,
                error TEXT
            )
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_activities_timestamp
            ON activities(timestamp DESC)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_activities_type
            ON activities(type)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_activities_workflow_id
            ON activities(workflow_id)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_activities_batch_id
            ON activities(batch_id)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_activities_thread_id
            ON activities(thread_id)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_activities_level
            ON activities(level)
        """)

        logger.info("Activity tables migration completed")

    except Exception as e:
        logger.warning(f"Activity tables migration failed: {e}")


def migrate_checkpoint_tables(conn) -> None:
    """Ensure LangGraph checkpoint tables exist.

    Creates the checkpoints and checkpoint_writes tables for workflow
    state persistence. This enables viewing Graph history in Activity sidebar.
    """
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS checkpoints (
                thread_id TEXT NOT NULL,
                checkpoint_ns TEXT NOT NULL DEFAULT '',
                checkpoint_id TEXT NOT NULL,
                parent_checkpoint_id TEXT,
                type TEXT,
                checkpoint BLOB,
                metadata BLOB,
                PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS checkpoint_writes (
                thread_id TEXT NOT NULL,
                checkpoint_ns TEXT NOT NULL DEFAULT '',
                checkpoint_id TEXT NOT NULL,
                task_id TEXT NOT NULL,
                idx INTEGER NOT NULL,
                channel TEXT NOT NULL,
                type TEXT,
                value BLOB,
                PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, idx)
            )
        """)

        logger.info("Checkpoint tables migration completed")

    except Exception as e:
        logger.warning(f"Checkpoint tables migration failed: {e}")
