"""Regression: app.duckdb persists across versions, so a `devices` table created
before `expires_at` existed (#2173) must be migrated in place — `CREATE TABLE IF
NOT EXISTS` will not add the column, which previously broke AppDatabase.__init__
and 500'd every app-DB endpoint (providers, ai-defaults, ...)."""

from __future__ import annotations


from fichero_server.db.app import AppDatabase


def _make_legacy_devices_db(path) -> None:
    """Produce an app.duckdb whose devices table predates the expires_at column.

    Build the real, current schema once (so users/FKs are correct), then drop
    expires_at and insert a legacy row — faithfully reproducing a DB created
    before #2173 without hand-maintaining the full schema here.
    """
    db = AppDatabase(path=path)
    # Insert a user satisfying whatever NOT NULL columns the real schema has
    # (type-appropriate values), so the devices FK is valid without hand-tracking
    # the users schema.
    from datetime import datetime

    def _value(name: str, col_type: str):
        if name == "id":
            return "u1"
        t = col_type.upper()
        if "BOOL" in t:
            return False
        if "INT" in t or "DECIMAL" in t or "DOUBLE" in t or "FLOAT" in t:
            return 0
        if "TIMESTAMP" in t or "DATE" in t:
            return datetime(2026, 1, 1)
        return "legacy"

    user_cols = db.conn.execute("PRAGMA table_info(users)").fetchall()
    names = [c[1] for c in user_cols]
    values = [_value(c[1], c[2]) for c in user_cols]
    placeholders = ", ".join("?" for _ in names)
    db.conn.execute(
        f"INSERT INTO users ({', '.join(names)}) VALUES ({placeholders})", values
    )
    # Recreate devices in its actual pre-#2173 shape (no expires_at). DuckDB
    # refuses DROP COLUMN when an index exists, so rebuild the table instead —
    # this matches the legacy schema observed on real installs.
    db.conn.execute("DROP TABLE devices")
    db.conn.execute(
        """
        CREATE TABLE devices (
            id VARCHAR PRIMARY KEY,
            name VARCHAR NOT NULL,
            user_id VARCHAR NOT NULL,
            token_hash VARCHAR NOT NULL UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            revoked BOOLEAN DEFAULT FALSE,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
        """
    )
    db.conn.execute(
        "INSERT INTO devices (id, name, user_id, token_hash, created_at) "
        "VALUES ('d1', 'iPad', 'u1', 'hash1', TIMESTAMP '2026-01-01 00:00:00')"
    )
    db.conn.close()


def test_legacy_devices_table_is_migrated_with_expires_at(tmp_path) -> None:
    db_path = tmp_path / "app.duckdb"
    _make_legacy_devices_db(str(db_path))

    # Opening with the current code must NOT raise and must add the column.
    db = AppDatabase(path=db_path)
    cols = {row[1] for row in db.conn.execute("PRAGMA table_info(devices)").fetchall()}
    assert "expires_at" in cols, f"expires_at not migrated in: {sorted(cols)}"

    # Existing paired devices are backfilled (created_at + 90d), not left NULL,
    # preserving the NOT-NULL invariant fresh schemas enforce.
    expires_at, created_at = db.conn.execute(
        "SELECT expires_at, created_at FROM devices WHERE id = 'd1'"
    ).fetchone()
    assert expires_at is not None, "existing device row left with NULL expires_at"
    assert expires_at > created_at, "backfilled expiry must be after creation"

    # App-DB endpoints that previously 500'd now work.
    assert isinstance(db.get_ai_defaults(), dict)


def test_migration_is_idempotent(tmp_path) -> None:
    db_path = tmp_path / "app.duckdb"
    _make_legacy_devices_db(str(db_path))
    AppDatabase(path=db_path)  # first migrates
    # Second open must not error or duplicate the column.
    db2 = AppDatabase(path=db_path)
    cols = [row[1] for row in db2.conn.execute("PRAGMA table_info(devices)").fetchall()]
    assert cols.count("expires_at") == 1
