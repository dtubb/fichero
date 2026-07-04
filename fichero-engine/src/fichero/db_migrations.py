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

        # Idempotent per-column checks for columns added after the initial
        # steps→format migration. Each runs regardless of the old-schema gate
        # above so fresh-installed tables also pick them up if the model
        # evolved past _ensure_table's snapshot.
        result = conn.execute("PRAGMA table_info('workflows')").fetchall()
        columns = {row[1] for row in result}

        if "is_system" not in columns:
            logger.info("Migrating workflows table: adding is_system column...")
            conn.execute("""
                ALTER TABLE workflows
                ADD COLUMN is_system BOOLEAN DEFAULT FALSE
            """)
            # Backfill any NULLs that may exist from a partial prior migration.
            conn.execute("""
                UPDATE workflows SET is_system = FALSE WHERE is_system IS NULL
            """)

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


def migrate_knowledge_indices(conn) -> None:
    """Add indices on knowledgeentitys + knowledgeclaims for fast lookup.

    Note the table names use the Pythonic ``_ensure_table`` convention
    (model name lowercased + 's' → ``knowledgeclaims``, ``knowledgeentitys``).
    Activities and provider_refs already had indices; the knowledge tables
    didn't, which meant every ``WHERE source_document_id = ?`` ran a full
    table scan. At 50K claims that's noticeable; at 1M claims it's
    seconds per query.

    These are the indices the wireframe (View 1 inspector, View 4 source
    preview, claim-search) hits hardest. IF NOT EXISTS so safe to re-run.
    Each statement is wrapped in its own try/except — a missing table
    silently no-ops and the next call picks it up after the tables get
    lazily created by ``_ensure_table``. (#991 — scaling-review bottleneck 2)
    """
    # DuckDB ART secondary indexes can become desynchronised from the table
    # heap after sustained update/delete churn and then raise a FATAL
    # "Failed to delete all rows from index" error. Both KnowledgeEntity AND
    # KnowledgeClaim rows churn heavily during catalogue dedup/rewrite (the
    # catalogue churns claims hardest of all), so keep their lookups on a table
    # scan until DuckDB's ART delete path is safe for this workload. Dropping
    # these indexes is data-safe — they only bought lookup speed, and at
    # Fichero's single-library scale a plain table scan is fine; correctness is
    # unaffected. The PRIMARY KEY index on ``id`` stays on each table: ``id`` is
    # a stable UUID that is never UPDATEd, so its ART delete path isn't churned
    # the same way, and dropping a PK is not safe.
    #
    # #1596 dropped ``idx_entities_name`` for exactly this reason. The claims
    # ART indexes (``idx_claims_*``) hit the same corruption on the
    # ``knowledgeclaims`` table during real-data catalogue use (#1611), so they
    # are dropped here too. Existing libraries that already created any of these
    # (and are therefore one bad catalogue away from the crash) shed them here
    # — DROP INDEX IF EXISTS is idempotent and a no-op on fresh DBs.
    drop_indexes = [
        "idx_entities_name",
        "idx_claims_source_doc",
        "idx_claims_page",
        "idx_claims_type",
        "idx_claims_status",
        "idx_claims_created",
    ]
    for index_name in drop_indexes:
        try:
            conn.execute(f"DROP INDEX IF EXISTS {index_name}")
        except Exception as exc:
            logger.warning("Knowledge index %s drop skipped: %s", index_name, exc)

    # All knowledgeclaims/knowledgeentitys secondary ART indexes are now
    # dropped above (corruption risk). No CREATE INDEX statements remain for
    # these tables — queries fall back to table scans, which is correct and
    # fine at single-user scale. Keep this list empty rather than re-adding any
    # claims/entity index until DuckDB's ART delete path is safe for the churn.
    statements: list[tuple[str, str]] = []
    created = 0
    for name, ddl in statements:
        try:
            conn.execute(ddl)
            created += 1
        except Exception as exc:
            # Most common cause: the table doesn't exist yet (no claims
            # have been written, so _ensure_table hasn't run). Quietly
            # skip — next call after the first write picks it up.
            logger.debug("Knowledge index %s skipped: %s", name, exc)
    if created:
        logger.info("Knowledge indices migration: %d/%d indices ensured",
                    created, len(statements))


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


def migrate_known_libraries_table(conn) -> None:
    """Ensure known_libraries registry table exists (#1131).

    Stores a persistent registry of known .fichero libraries for CLI
    operations (list available libraries, switch between them).
    """
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS known_libraries (
                id VARCHAR PRIMARY KEY,
                path VARCHAR UNIQUE NOT NULL,
                name VARCHAR,
                added_at TIMESTAMP NOT NULL,
                last_accessed TIMESTAMP NOT NULL
            )
        """)
        logger.info("Known libraries registry table migration completed")
    except Exception as e:
        logger.warning("Known libraries table migration failed: %s", e)


def migrate_references_table(conn) -> None:
    """Ensure references storage exists (#1103).

    References are first-class bibliographic records, separate from the
    documents they may eventually map to.
    """

    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS "references" (
                id VARCHAR PRIMARY KEY,
                bibtex TEXT NOT NULL,
                authors JSON DEFAULT '[]',
                title VARCHAR DEFAULT '',
                year INTEGER,
                kind VARCHAR NOT NULL DEFAULT 'misc',
                journal_or_book VARCHAR,
                publisher VARCHAR,
                doi VARCHAR,
                isbn VARCHAR,
                pages VARCHAR,
                language VARCHAR,
                verification_score DOUBLE,
                verification_source VARCHAR,
                verified_at TIMESTAMP,
                realized_as_document_id VARCHAR,
                notes TEXT DEFAULT '',
                tags JSON DEFAULT '[]',
                status VARCHAR NOT NULL DEFAULT 'to_find',
                metadata JSON DEFAULT '{}',
                created_at TIMESTAMP NOT NULL,
                updated_at TIMESTAMP NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_references_doi
            ON "references"(doi)
            """
        )
        conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_references_isbn
            ON "references"(isbn)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_references_authors_year
            ON "references"(authors, year)
            """
        )
        logger.info("References table migration completed")
    except Exception as e:
        logger.warning("References table migration failed: %s", e)


def migrate_reference_provenance_table(conn) -> None:
    """Ensure reference provenance tracking exists (#1103)."""

    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS reference_provenance (
                id VARCHAR PRIMARY KEY,
                reference_id VARCHAR NOT NULL,
                document_id VARCHAR NOT NULL,
                page VARCHAR,
                span_start INTEGER,
                span_end INTEGER,
                citation_location VARCHAR NOT NULL DEFAULT 'unknown',
                created_at TIMESTAMP NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_reference_provenance_reference
            ON reference_provenance(reference_id)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_reference_provenance_document
            ON reference_provenance(document_id)
            """
        )
        logger.info("Reference provenance table migration completed")
    except Exception as e:
        logger.warning("Reference provenance table migration failed: %s", e)


def migrate_library_entity_types_table(conn) -> None:
    """Ensure library_entity_types table exists (#874).

    Per-library entity type customization: links each library to the
    entity_type ClassificationValue keys it allows for extraction.
    """
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS library_entity_types (
                id VARCHAR PRIMARY KEY,
                library_id VARCHAR NOT NULL,
                entity_type_key VARCHAR NOT NULL,
                enabled BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP NOT NULL,
                updated_at TIMESTAMP NOT NULL,
                UNIQUE(library_id, entity_type_key)
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_library_entity_types_library
            ON library_entity_types(library_id)
        """)
        logger.info("Library entity types table migration completed")
    except Exception as e:
        logger.warning("Library entity types table migration failed: %s", e)


def migrate_spatial_node_layout_fields(conn) -> None:
    """Add 2D/3D layout + style fields to spatialnode table (#2293).

    Existing rows keep their positions; new columns default to 0 / empty dict.
    Idempotent: skips columns that already exist and skips entirely if the
    table hasn't been created yet (first-launch path uses _ensure_table).
    """
    NEW_COLUMNS = [
        ("pos_w", "DOUBLE DEFAULT 0.0"),
        ("pos_h", "DOUBLE DEFAULT 0.0"),
        ("z_index", "INTEGER DEFAULT 0"),
        ("depth", "DOUBLE DEFAULT 0.0"),
        ("angle", "DOUBLE DEFAULT 0.0"),
        ("style_data", "VARCHAR DEFAULT '{}'"),
    ]
    try:
        table_exists = (
            conn.execute("""
                SELECT COUNT(*) FROM information_schema.tables
                WHERE table_name = 'spatialnode'
            """).fetchone()[0]
            > 0
        )
        if not table_exists:
            logger.debug("spatialnode table does not exist, skipping layout migration")
            return

        existing = {row[1] for row in conn.execute("PRAGMA table_info('spatialnode')").fetchall()}
        for col, col_def in NEW_COLUMNS:
            if col not in existing:
                logger.info("Migrating spatialnode: adding %s column", col)
                conn.execute(f"ALTER TABLE spatialnode ADD COLUMN {col} {col_def}")

        logger.info("spatialnode layout fields migration completed")
    except Exception as e:
        logger.warning("spatialnode layout migration failed: %s", e)


def migrate_canvas_layout_table(conn) -> None:
    """Ensure the real canvas_layout table exists and backfill legacy document positions.

    #3078 retires the document-row-only persistence path. Keep old saved folder
    layouts by copying any document position/style data into the dedicated table
    the first time a library sees this migration. Idempotent: create-if-missing
    plus insert-only-when-absent on the deterministic ``scope_id::item_id`` key.
    """
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS canvas_layout (
                id VARCHAR PRIMARY KEY,
                folder_id VARCHAR NOT NULL,
                item_id VARCHAR NOT NULL,
                x DOUBLE DEFAULT 0.0,
                y DOUBLE DEFAULT 0.0,
                z DOUBLE DEFAULT 0.0,
                w DOUBLE,
                h DOUBLE,
                d DOUBLE,
                angle DOUBLE DEFAULT 0.0,
                z_index INTEGER DEFAULT 0,
                style VARCHAR,
                updated_at TIMESTAMP NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_canvas_layout_scope
            ON canvas_layout(folder_id)
            """
        )
        documents_exists = (
            conn.execute(
                """
                SELECT COUNT(*) FROM information_schema.tables
                WHERE table_name = 'documents'
                """
            ).fetchone()[0]
            > 0
        )
        if not documents_exists:
            logger.debug("documents table does not exist, skipping canvas_layout backfill")
            return
        conn.execute(
            """
            INSERT INTO canvas_layout (
                id, folder_id, item_id, x, y, z, w, h, d, angle, z_index, style, updated_at
            )
            SELECT
                parent_id || '::' || id,
                parent_id,
                id,
                COALESCE(position_x, 0.0),
                COALESCE(position_y, 0.0),
                COALESCE(position_z, 0.0),
                TRY_CAST(json_extract(metadata, '$.canvas_w') AS DOUBLE),
                TRY_CAST(json_extract(metadata, '$.canvas_h') AS DOUBLE),
                TRY_CAST(json_extract(metadata, '$.canvas_d') AS DOUBLE),
                COALESCE(rotation_z, 0.0),
                COALESCE(z_index, 0),
                json_extract_string(metadata, '$.canvas_style'),
                COALESCE(updated_at, CURRENT_TIMESTAMP)
            FROM documents d
            WHERE parent_id IS NOT NULL
              AND (
                position_x IS NOT NULL
                OR position_y IS NOT NULL
                OR position_z IS NOT NULL
                OR rotation_z IS NOT NULL
                OR COALESCE(z_index, 0) != 0
                OR json_extract(metadata, '$.canvas_w') IS NOT NULL
                OR json_extract(metadata, '$.canvas_h') IS NOT NULL
                OR json_extract(metadata, '$.canvas_d') IS NOT NULL
                OR json_extract(metadata, '$.canvas_style') IS NOT NULL
              )
              AND NOT EXISTS (
                SELECT 1
                FROM canvas_layout c
                WHERE c.id = parent_id || '::' || d.id
              )
            """
        )
        logger.info("canvas_layout table migration completed")
    except Exception as e:
        logger.warning("canvas_layout migration failed: %s", e)
