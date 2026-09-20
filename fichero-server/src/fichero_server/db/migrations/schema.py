"""
DuckDB schema migrations for Fichero.

Each function takes an open DuckDB connection and is idempotent.
Called by Database.__init__ and DatabaseManager.get_database.

#4983 phase 1 (atomic + loud + recorded, deliberately NOT "refuse to open" —
that is phase 2, for the maintainer to decide with evidence from phase 1 in
hand): every migration below that issues several statements now runs them
as ONE transaction via `_run_atomic_migration`, so a failure partway leaves
the schema exactly as it was, never half-applied. DuckDB's DDL and UPDATE
backfills are fully transactional (verified directly: ALTER ADD COLUMN,
CREATE INDEX, CREATE UNIQUE INDEX and UPDATE all roll back together inside
one BEGIN/ROLLBACK) — no statement kind used here needed an exception to
that.

The helper logs at ERROR and appends a `MigrationFailure` to the caller's
`failures` list, then swallows — the library still opens, exactly as every
migration in this file did before this phase. Two swallows are intentionally
LEFT AS interior try/excepts, not routed through the helper (see their own
functions for why): the `DROP INDEX IF EXISTS` loop in
`migrate_knowledge_indices`, and `read_library_uuid`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import logging
from typing import Callable

from fichero_server.core.timeutil import utc_now

logger = logging.getLogger(__name__)


@dataclass
class MigrationFailure:
    """One recorded schema-migration failure (#4983 phase 1).

    Not a Pydantic model — this lives at the persistence layer, not the API
    layer. `api/main.py`'s health route converts a `Database`'s
    `migration_failures` list into the API response shape.
    """

    migration: str
    error_type: str
    message: str
    occurred_at: datetime


def _run_atomic_migration(
    conn,
    name: str,
    step: Callable[[], None],
    failures: list[MigrationFailure] | None = None,
    *,
    swallow: bool = True,
) -> None:
    """Run one migration's statements as ONE transaction (#4983 phase 1).

    On failure: ROLLBACK (the schema is left exactly as it was — nothing
    partially applied), log at ERROR with `name` and the exception, and
    append a `MigrationFailure` to `failures` (a bare `None` default keeps
    every existing call site — many tests pass a raw in-memory `conn` with
    no failures list at all — working unchanged; the two real callers,
    `Database.__init__` and `DatabaseManager.get_database`, pass a real
    shared list so a failure looks the same from either).

    `swallow=False` (used only by `migrate_workflow_table`, the one
    migration that already raised before this phase) still rolls back,
    logs and records, but then re-raises — preserving that function's
    existing "fails loudly" contract instead of quietly changing it under
    a phase-1 sweep the maintainer did not ask to widen.

    Defensive against a nested transaction: BEGIN itself is inside the
    try (traced both real call sites — `Database.__init__` runs on a
    connection that was JUST opened by `_connect()`, before anything else
    could start a transaction on it; `DatabaseManager.get_database` calls
    this only after `Database.__init__` has already returned, by which
    point every transaction it opened has been committed or rolled back —
    so a nested BEGIN cannot happen today). If it ever did (DuckDB raises
    immediately: "cannot start a transaction within a transaction"),
    ROLLBACK is skipped (nothing of THIS call's to roll back) and the
    failure is still logged and recorded rather than propagating raw.
    """
    if failures is None:
        failures = []
    began = False
    try:
        conn.execute("BEGIN TRANSACTION")
        began = True
        step()
        conn.execute("COMMIT")
    except Exception as exc:
        message = str(exc)
        if began:
            try:
                conn.execute("ROLLBACK")
            except Exception as rollback_exc:
                # Not a bare log-and-drop: folded into the SAME failure
                # record below, so a rollback that itself failed is never
                # less visible than an ordinary migration failure.
                message = f"{message} (ROLLBACK also failed: {rollback_exc})"
        logger.error("Migration '%s' failed and was rolled back: %s", name, message)
        failures.append(
            MigrationFailure(
                migration=name,
                error_type=type(exc).__name__,
                message=message,
                occurred_at=utc_now(),
            )
        )
        if not swallow:
            raise


def migrate_paired_device_owner(conn) -> None:
    """Fold the retired pairing owner into the canonical owner account.

    Early single-user pairing created ``__paired_device_owner__`` while the
    auth middleware created ``owner``.  When both rows exist, resolve every
    device and library-role reference to ``owner`` before disabling the
    retired row.  A sole legacy row is deliberately left alone: it remains a
    real account and this migration must not invent or discard user data.
    """
    canonical = conn.execute(
        "SELECT id FROM users WHERE username = ?", ["owner"]
    ).fetchone()
    legacy = conn.execute(
        "SELECT id FROM users WHERE username = ?", ["__paired_device_owner__"]
    ).fetchone()
    if canonical is None or legacy is None:
        return

    canonical_id, legacy_id = canonical[0], legacy[0]
    if canonical_id == legacy_id:
        return

    conn.execute(
        "UPDATE devices SET user_id = ? WHERE user_id = ?", [canonical_id, legacy_id]
    )

    # ``library_roles`` is unique per (user, library), so preserve the
    # canonical row when both identities already have a role for one library.
    legacy_roles = conn.execute(
        "SELECT id, library_path, role FROM library_roles WHERE user_id = ?",
        [legacy_id],
    ).fetchall()
    role_rank = {"viewer": 1, "editor": 2, "owner": 3}
    for role_id, library_path, role in legacy_roles:
        existing = conn.execute(
            "SELECT id, role FROM library_roles WHERE user_id = ? AND library_path = ?",
            [canonical_id, library_path],
        ).fetchone()
        if existing is None:
            conn.execute(
                "UPDATE library_roles SET user_id = ? WHERE id = ?",
                [canonical_id, role_id],
            )
        else:
            existing_id, existing_role = existing
            if role_rank.get(role, 0) > role_rank.get(existing_role, 0):
                conn.execute(
                    "UPDATE library_roles SET role = ? WHERE id = ?",
                    [role, existing_id],
                )
            conn.execute("DELETE FROM library_roles WHERE id = ?", [role_id])

    conn.execute("UPDATE users SET active = FALSE WHERE id = ?", [legacy_id])
    conn.commit()


def migrate_workflow_table(
    conn, failures: list[MigrationFailure] | None = None
) -> None:
    """Migrate workflows table to new schema if needed.

    #4983 phase 1: NOT wrapped in `_run_atomic_migration` — the one
    migration in this file left non-atomic, on purpose, verified. DuckDB
    1.5.5's transactional DDL does not cover this shape: `ALTER TABLE ...
    ADD COLUMN ... JSON DEFAULT []` on a table with existing rows requires
    materialising that default across every row, and a SECOND statement of
    ANY kind against the same table inside the same explicit transaction
    then fails on COMMIT with `TransactionException: ... another
    transaction has altered this table` (reproduced directly: one such
    ALTER alone commits fine; a second ALTER, even a trivial scalar-default
    one, right after it does not). This migration has three `DEFAULT []`
    columns (`nodes`, `edges`, `tags`) plus six more statements against the
    same table — there is no way to make it one transaction under this
    engine version. Per the phase-1 instruction ("where one does not
    cover it, say so and leave that migration as it is"): left exactly as
    it was — still raises after logging. `failures` IS populated on this
    path (recorded, then re-raised) so a caller/operator inspecting
    `Database.migration_failures` sees this one too, even though the
    library never actually opens on this specific failure (see the
    call-site note below on what the app sees).
    """
    if failures is None:
        failures = []
    try:
        _migrate_workflow_table_body(conn)
    except Exception as e:
        logger.warning("Migration failed: %s", e)
        failures.append(
            MigrationFailure(
                migration="migrate_workflow_table",
                error_type=type(e).__name__,
                message=str(e),
                occurred_at=utc_now(),
            )
        )
        raise


def _migrate_workflow_table_body(conn) -> None:
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


def migrate_document_table(
    conn, failures: list[MigrationFailure] | None = None
) -> None:
    """Migrate documents table to add the sort_order column.

    Older installations (pre-0.0.2 reorder work, pre-`#607`) created the
    documents table without `sort_order`. The Pydantic Document model
    now includes `sort_order: int = 0`, so every `INSERT OR REPLACE INTO
    documents` fails with a DuckDB Binder Error ("does not have a column
    with name sort_order"). Seen in a 2026-04-18 reproduction:

        _duckdb.BinderException: Binder Error: Table "documents" does
        not have a column with name "sort_order". Did you mean: "id"

    Fix: ALTER TABLE the existing documents table to add the column
    with default 0. Idempotent — skips if the column already exists,
    or if the table hasn't been created yet (first-launch path uses
    `_ensure_table` which picks up the current schema automatically).

    #4983 phase 1: this is the migration the issue named — three
    independent statements (two `ALTER TABLE ADD COLUMN` + one
    `CREATE INDEX`), previously with no transaction, so a failure between
    them left the library with `sort_order` added but not
    `exclude_from_search`, silently. Now atomic: all three or none.
    """

    def _step() -> None:
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

        # #4580: search exclusion is its own flag, separate from
        # exclude_from_processing — both are user curation, so existing
        # libraries need the column, not just fresh `_ensure_table` schemas.
        if "exclude_from_search" not in columns:
            logger.info("Migrating documents table: adding exclude_from_search column...")
            conn.execute("""
                ALTER TABLE documents
                ADD COLUMN exclude_from_search BOOLEAN DEFAULT FALSE
            """)

        # Listing hot path (perf audit 2026-08-19): every folder browse and
        # child-count aggregate filters on parent_id; without an index each
        # one full-scans the table — untenable at the 1M-document target.
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_documents_parent_id "
            "ON documents(parent_id)"
        )

        logger.info("Documents table migration completed")

    _run_atomic_migration(conn, "migrate_document_table", _step, failures)


def migrate_document_language_fields(
    conn, failures: list[MigrationFailure] | None = None
) -> None:
    """Add `language` / `language_meta` to documents (#2092).

    The Pydantic Document model gained both fields, so an existing library
    would fail every `INSERT OR REPLACE INTO documents` with a DuckDB Binder
    Error until the columns exist — the same failure mode `sort_order` hit.

    BACKFILL: both columns are left NULL for every existing row, on purpose.

    NULL `language_meta` is not an absence of data, it is a statement:
    "nothing has ever determined this document's language". Writing 'English'
    into it would be a fabrication, and on this archive — Spanish-language
    colonial material — a fabrication that is usually wrong while looking
    exactly like a real answer. There is no correct value to backfill because
    the fact was never recorded at ingest; the honest backfill is to say so and
    let the language-identification pass fill it in. Note that this is distinct
    from `language_meta["status"] == "unknown"`, which means detection DID run
    and could not tell. A user needs those apart: the first says "run it", the
    second says "this one needs a person".

    Idempotent: skips columns that already exist, and skips entirely if the
    table has not been created yet (first launch materialises the current
    schema directly).
    """
    def _step() -> None:
        table_exists = (
            conn.execute("""
            SELECT COUNT(*) FROM information_schema.tables
            WHERE table_name = 'documents'
        """).fetchone()[0]
            > 0
        )
        if not table_exists:
            logger.debug("Documents table does not exist, skipping language migration")
            return

        result = conn.execute("PRAGMA table_info('documents')").fetchall()
        columns = {row[1] for row in result}

        if "language" not in columns:
            logger.info("Migrating documents table: adding language column...")
            conn.execute("ALTER TABLE documents ADD COLUMN language VARCHAR")

        if "language_meta" not in columns:
            logger.info("Migrating documents table: adding language_meta column...")
            conn.execute("ALTER TABLE documents ADD COLUMN language_meta JSON")

        logger.info("Documents language migration completed")

    _run_atomic_migration(conn, "migrate_document_language_fields", _step, failures)


def migrate_saved_search_table(
    conn, failures: list[MigrationFailure] | None = None
) -> None:
    """Migrate saved_searches table to add missing columns."""

    def _step() -> None:
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

    _run_atomic_migration(conn, "migrate_saved_search_table", _step, failures)


def migrate_provider_refs_table(
    conn, failures: list[MigrationFailure] | None = None
) -> None:
    """Create provider_refs table if it doesn't exist.

    This table tracks which app-wide providers a library references.
    Actual provider config is stored in app.duckdb.
    """

    def _step() -> None:
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

    _run_atomic_migration(conn, "migrate_provider_refs_table", _step, failures)


def migrate_activity_tables(
    conn, failures: list[MigrationFailure] | None = None
) -> None:
    """Ensure activity tracking tables exist.

    Creates the activities table for storing workflow execution events.
    This enables the Activity sidebar to show historical data.

    #4983 item 6, traced end to end (was INFERRED, now VERIFIED): if this
    migration fails and rolls back, `ActivityStore._init_database()`
    (`workflows/activity_store.py`) DOES independently re-create the same
    `activities` TABLE the first time `get_activity_tracker(db_path)` is
    called for this library — but that call is LAZY (fired by the first
    activity-logging code path, e.g. a workflow run), not guaranteed at
    open time, and it does NOT recreate this migration's 6 performance
    indices. So the table itself is very likely papered over eventually;
    the indices are not, and a library that never runs a workflow in a
    session may go the whole session without either.
    """

    def _step() -> None:
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

    _run_atomic_migration(conn, "migrate_activity_tables", _step, failures)


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
    # #4983 phase 1: LEFT AS an interior per-item try/except, not routed
    # through `_run_atomic_migration` — this is one of the two swallows the
    # sweep judged genuinely defensible. Each DROP is independent and
    # idempotent by construction (IF EXISTS); a real failure here is
    # "the index was already gone," never a half-applied state to roll
    # back, and batching six independent drops into one transaction would
    # only make one unrelated failure block the other five for no reason.
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
    # #4983 phase 1: also left as an interior swallow, for the same reason —
    # `statements` is empty today, so this loop is dead; if it is ever
    # populated, each entry is independent and idempotent (IF NOT EXISTS)
    # the same way the drops above are.
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


def migrate_checkpoint_tables(
    conn, failures: list[MigrationFailure] | None = None
) -> None:
    """Ensure LangGraph checkpoint tables exist.

    Creates the checkpoints and checkpoint_writes tables for workflow
    state persistence. This enables viewing Graph history in Activity sidebar.
    """

    def _step() -> None:
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

    _run_atomic_migration(conn, "migrate_checkpoint_tables", _step, failures)


def migrate_known_libraries_table(
    conn, failures: list[MigrationFailure] | None = None
) -> None:
    """Ensure known_libraries registry table exists (#1131).

    Stores a persistent registry of known .fichero libraries for CLI
    operations (list available libraries, switch between them).
    """

    def _step() -> None:
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

    _run_atomic_migration(conn, "migrate_known_libraries_table", _step, failures)


def migrate_references_table(
    conn, failures: list[MigrationFailure] | None = None
) -> None:
    """Ensure references storage exists (#1103).

    References are first-class bibliographic records, separate from the
    documents they may eventually map to.

    #4983 phase 1: the two `CREATE UNIQUE INDEX` statements (DOI, ISBN) are
    the only thing enforcing "no duplicate reference by DOI/ISBN" — the
    highest-stakes migration in this file for silent swallowing, since a
    failed unique index used to mean the constraint just didn't exist, with
    duplicate inserts succeeding uncaught afterward. Now atomic with the
    table and the perf index: any failure rolls all four statements back
    and is recorded, rather than leaving the constraint quietly absent.
    """

    def _step() -> None:
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

    _run_atomic_migration(conn, "migrate_references_table", _step, failures)


def migrate_reference_provenance_table(
    conn, failures: list[MigrationFailure] | None = None
) -> None:
    """Ensure reference provenance tracking exists (#1103)."""

    def _step() -> None:
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

    _run_atomic_migration(conn, "migrate_reference_provenance_table", _step, failures)


def migrate_library_entity_types_table(
    conn, failures: list[MigrationFailure] | None = None
) -> None:
    """Ensure library_entity_types table exists (#874).

    Per-library entity type customization: links each library to the
    entity_type ClassificationValue keys it allows for extraction.
    """

    def _step() -> None:
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

    _run_atomic_migration(conn, "migrate_library_entity_types_table", _step, failures)


def migrate_spatial_node_layout_fields(
    conn, failures: list[MigrationFailure] | None = None
) -> None:
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

    def _step() -> None:
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

    _run_atomic_migration(conn, "migrate_spatial_node_layout_fields", _step, failures)


def migrate_canvas_layout_table(
    conn, failures: list[MigrationFailure] | None = None
) -> None:
    """Ensure the real canvas_layout table exists and backfill legacy document positions.

    #3078 retires the document-row-only persistence path. Keep old saved folder
    layouts by copying any document position/style data into the dedicated table
    the first time a library sees this migration. Idempotent: create-if-missing
    plus insert-only-when-absent on the deterministic ``scope_id::item_id`` key.
    """

    def _step() -> None:
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

    _run_atomic_migration(conn, "migrate_canvas_layout_table", _step, failures)


def migrate_catalogue_chunk_artifact_type(
    conn, failures: list[MigrationFailure] | None = None
) -> None:
    """Collapse ``catalogue.chunk.{n}`` artifact types to ``catalogue.chunk`` (#4426).

    The catalogue tool used to mint a NEW artifact_type per summary chunk —
    ``catalogue.chunk.1``, ``catalogue.chunk.2``, … — which made the
    artifact_type vocabulary unbounded. That is what prevented the field being
    declared as an enum in the OpenAPI schema, and a bare ``str`` there is why
    #4418 could ship as two green commits and one dead feature: the generated
    Swift client exposes a String, so a server/client mismatch has nothing to
    fail against.

    The writer now emits a stable ``catalogue.chunk`` with the index in
    ``data``. This repoints rows already on disk, so a library catalogued
    before the change does not keep unbounded types alive — real archival data
    is never regenerated from scratch, so the rows have to be migrated rather
    than waited out.

    Idempotent: the LIKE pattern matches only the old dotted form, so a second
    run updates nothing. The chunk index moves into ``data`` to match what the
    writer now records.
    """
    def _step() -> None:
        table_exists = (
            conn.execute(
                """
            SELECT COUNT(*) FROM information_schema.tables
            WHERE table_name = 'artifacts'
        """
            ).fetchone()[0]
            > 0
        )
        if not table_exists:
            logger.debug("artifacts table absent; skipping chunk-type migration")
            return

        pending = conn.execute(
            "SELECT COUNT(*) FROM artifacts WHERE artifact_type LIKE 'catalogue.chunk.%'"
        ).fetchone()[0]
        if not pending:
            return

        conn.execute(
            """
            UPDATE artifacts
               SET data = json_object(
                       'chunk_index',
                       TRY_CAST(
                           split_part(artifact_type, 'catalogue.chunk.', 2) AS INTEGER
                       )
                   ),
                   artifact_type = 'catalogue.chunk'
             WHERE artifact_type LIKE 'catalogue.chunk.%'
            """
        )
        logger.info(
            "Migrated %d catalogue.chunk.N artifact(s) to the stable "
            "'catalogue.chunk' type (#4426)",
            pending,
        )

    _run_atomic_migration(conn, "migrate_catalogue_chunk_artifact_type", _step, failures)


def migrate_library_identity_table(
    conn, failures: list[MigrationFailure] | None = None
) -> None:
    """Mint a stable per-library UUID for sync identity (D1).

    ``actions/audit_chain.py`` derives ``library_id = sha256(library_path)``,
    which changes the moment the package is moved or renamed — wrong as a *sync*
    identity, because a moved library must still be recognized as the same
    library by the peers it syncs with (design
    ``agent-work/design/hpc-remote-library-sync.md`` §7 D1). This table holds a
    single row: a UUID minted once, at first open, and stable for the life of
    the package regardless of where it lives on disk.

    Idempotent: creates the table if absent and inserts exactly one row if it is
    empty; a second run finds the row and does nothing. The path hash stays as
    the audit-chain key — this is an additive identity, not a replacement.
    """
    from uuid import uuid4

    def _step() -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS library_identity (
                singleton BOOLEAN PRIMARY KEY DEFAULT TRUE,
                library_uuid VARCHAR NOT NULL,
                minted_at TIMESTAMP NOT NULL
            )
            """
        )
        row = conn.execute("SELECT COUNT(*) FROM library_identity").fetchone()
        if row is not None and row[0] == 0:
            conn.execute(
                "INSERT INTO library_identity (singleton, library_uuid, minted_at) "
                "VALUES (TRUE, ?, ?)",
                [str(uuid4()), utc_now()],
            )
        logger.info("Library identity table migration completed")

    _run_atomic_migration(conn, "migrate_library_identity_table", _step, failures)


def read_library_uuid(conn) -> str | None:
    """Return the library's stable sync UUID, or ``None`` if not yet minted.

    A thin reader over the single ``library_identity`` row (see
    :func:`migrate_library_identity_table`). Used by the sync layer to key
    manifests and checkpoints by a move-stable identity rather than the package
    path. Returns ``None`` rather than raising if the table is missing, so a
    caller on a not-yet-migrated library degrades gracefully.

    #4983 phase 1: LEFT AS its own try/except, not routed through the
    migration helper — this is not a migration (it writes nothing) and its
    swallow is the other one the sweep judged defensible: a missing table
    means "not yet minted," which is exactly the caller-visible `None` this
    function already promises, not a hidden failure.
    """
    try:
        row = conn.execute(
            "SELECT library_uuid FROM library_identity LIMIT 1"
        ).fetchone()
        return str(row[0]) if row and row[0] else None
    except Exception:
        return None
