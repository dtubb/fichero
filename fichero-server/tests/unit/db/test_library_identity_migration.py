"""Unit tests for the stable library-UUID migration (sync identity, D1).

See ``agent-work/design/hpc-remote-library-sync.md`` §7 D1. The migration mints
one move-stable UUID per library, idempotently.
"""

from fichero_server.core.duckdb_session import connect_utc
from fichero_server.db.migrations.schema import (
    migrate_library_identity_table,
    read_library_uuid,
)


def test_migration_mints_one_stable_uuid():
    conn = connect_utc(":memory:")
    migrate_library_identity_table(conn)
    uuid1 = read_library_uuid(conn)
    assert uuid1 is not None and len(uuid1) == 36  # canonical UUID string
    count = conn.execute("SELECT COUNT(*) FROM library_identity").fetchone()[0]
    assert count == 1


def test_migration_is_idempotent_and_uuid_is_stable():
    conn = connect_utc(":memory:")
    migrate_library_identity_table(conn)
    first = read_library_uuid(conn)
    # Re-running (e.g. every library open) must not re-mint or duplicate.
    migrate_library_identity_table(conn)
    migrate_library_identity_table(conn)
    assert read_library_uuid(conn) == first
    count = conn.execute("SELECT COUNT(*) FROM library_identity").fetchone()[0]
    assert count == 1


def test_read_library_uuid_none_before_migration():
    conn = connect_utc(":memory:")
    # No table yet — reader degrades to None rather than raising.
    assert read_library_uuid(conn) is None
