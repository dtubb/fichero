"""Every persisted `int` field holds a real 64-bit number (#5059).

Ruled 2026-09-26 by the maintainer: fix the Pydantic-to-DuckDB type system
rather than the one field that tripped over it.

THE DEFECT. `Database._python_to_duckdb_type` mapped Python `int` to DuckDB
`INTEGER`, which is INT32 and stops at 2,147,483,647. Python's `int` is
arbitrary-precision, so a field declared `int` reads as "any whole number" — and
a disk with 20 GB free is 20,688,982,016. Saving a record that stored free space
failed outright:

    _duckdb.ConversionException: Type INT64 with value 20688982016 can't be cast
    because the value is out of range for the destination type INT32

Found by handing a real value to the real database. A declaration that says one
thing while its storage says another is the day's recurring shape: the gap
between what someone meant and what the machine was handed.

**The map alone is not the fix, and the second test here is the important one.**
Changing the map helps libraries created afterwards; every EXISTING library keeps
its INTEGER columns and keeps the ceiling — including real research libraries,
which are the ones that matter. So `_ensure_table` widens narrow integer columns
in place on open, beside the ADD COLUMN reconcile that exists for the same reason.
INT32 to INT64 is lossless, so there is no backfill and no decision about data.
"""

from __future__ import annotations

import duckdb
import pytest
from pydantic import BaseModel, Field

from fichero_server.core.timeutil import utc_now
from fichero_server.db import Database

pytestmark = pytest.mark.source_model

#: The value that actually failed, not a synthetic one. 20 GB of free disk.
REAL_FAILING_VALUE = 20_688_982_016

#: Comfortably past INT32's ceiling, for the "does it really hold 64 bits" case.
BIG = 9_000_000_000_000


class _Measurement(BaseModel):
    """A model whose only interesting property is an `int` that means bytes."""

    id: str = Field(default="m1")
    free_bytes: int = 0
    small: int = 0


def _column_type(conn, table: str, column: str) -> str:
    for row in conn.execute(f"PRAGMA table_info({table})").fetchall():
        if row[1] == column:
            return str(row[2] or "").upper()
    raise AssertionError(f"{table}.{column} not found")


class TestTheTypeMap:
    def test_int_maps_to_bigint(self):
        mapper = Database.__new__(Database)
        assert mapper._python_to_duckdb_type(int) == "BIGINT"
        # And through Optional, which is how most fields are declared.
        assert mapper._python_to_duckdb_type(int | None) == "BIGINT"

    def test_a_fresh_library_stores_the_value_that_failed(self, tmp_path):
        db = Database(tmp_path / "fresh.duckdb")
        try:
            db.save(_Measurement(id="m1", free_bytes=REAL_FAILING_VALUE, small=42))

            stored = db.get(_Measurement, "m1")
            assert stored.free_bytes == REAL_FAILING_VALUE
            assert stored.small == 42
            assert _column_type(db.conn, "_measurements", "free_bytes") == "BIGINT"
        finally:
            db.close()

    def test_a_fresh_library_holds_a_genuinely_large_number(self, tmp_path):
        db = Database(tmp_path / "big.duckdb")
        try:
            db.save(_Measurement(id="m2", free_bytes=BIG))
            assert db.get(_Measurement, "m2").free_bytes == BIG
        finally:
            db.close()

    def test_the_conversion_report_stores_real_disk_numbers(self, tmp_path):
        """The record that found the defect, with the value that found it."""
        from fichero_server.models.conversion import ConversionRun, ConversionVerdict

        db = Database(tmp_path / "report.duckdb")
        try:
            run = ConversionRun(
                verdict=ConversionVerdict.refused_disk,
                disk_required_bytes=REAL_FAILING_VALUE * 2,
                disk_available_bytes=REAL_FAILING_VALUE,
            )
            db.save(run)

            stored = db.get(ConversionRun, run.id)
            assert stored.disk_available_bytes == REAL_FAILING_VALUE
            assert stored.disk_required_bytes == REAL_FAILING_VALUE * 2
        finally:
            db.close()


class TestAnExistingLibraryIsWidenedOnOpen:
    """The half that protects libraries that already exist.

    A library created before #5059 has INTEGER columns. Opening it must widen
    them, keep every row, and then accept a value that would have failed.
    """

    def _old_library(self, path) -> None:
        """A real DuckDB file with a NARROW column and rows already in it —
        hand-built, never produced by the current code, so it cannot silently
        become a fresh library the day the map changes again."""
        conn = duckdb.connect(str(path))
        conn.execute(
            "CREATE TABLE _measurements ("
            "  id VARCHAR PRIMARY KEY, free_bytes INTEGER, small INTEGER"
            ")"
        )
        conn.execute("INSERT INTO _measurements VALUES ('old-1', 1024, 7)")
        conn.execute("INSERT INTO _measurements VALUES ('old-2', 2048, 8)")
        assert _column_type(conn, "_measurements", "free_bytes") == "INTEGER"
        conn.close()

    def test_an_integer_column_is_widened_and_then_accepts_the_big_value(self, tmp_path):
        path = tmp_path / "old.duckdb"
        self._old_library(path)

        db = Database(path)
        try:
            # Opening is not enough on its own: the widening happens when the
            # table is reconciled, which is what `_ensure_table` does.
            db.save(_Measurement(id="new-1", free_bytes=REAL_FAILING_VALUE))

            assert _column_type(db.conn, "_measurements", "free_bytes") == "BIGINT"
            assert db.get(_Measurement, "new-1").free_bytes == REAL_FAILING_VALUE
        finally:
            db.close()

    def test_the_rows_that_were_already_there_are_unchanged(self, tmp_path):
        path = tmp_path / "old-rows.duckdb"
        self._old_library(path)

        db = Database(path)
        try:
            db.save(_Measurement(id="new-1", free_bytes=REAL_FAILING_VALUE))

            # INT32 to INT64 is lossless, so there is nothing to back-fill and
            # nothing to lose. Every pre-existing value reads back exactly.
            assert db.get(_Measurement, "old-1").free_bytes == 1024
            assert db.get(_Measurement, "old-1").small == 7
            assert db.get(_Measurement, "old-2").free_bytes == 2048
            assert db.get(_Measurement, "old-2").small == 8
        finally:
            db.close()

    def test_widening_twice_changes_nothing_the_second_time(self, tmp_path):
        path = tmp_path / "twice.duckdb"
        self._old_library(path)

        first = Database(path)
        try:
            first.save(_Measurement(id="new-1", free_bytes=REAL_FAILING_VALUE))
            after_first = {
                row[1]: str(row[2]).upper()
                for row in first.conn.execute("PRAGMA table_info(_measurements)").fetchall()
            }
            rows_after_first = sorted(
                first.conn.execute("SELECT id, free_bytes FROM _measurements").fetchall()
            )
        finally:
            first.close()

        second = Database(path)
        try:
            second.save(_Measurement(id="new-2", free_bytes=BIG))
            after_second = {
                row[1]: str(row[2]).upper()
                for row in second.conn.execute("PRAGMA table_info(_measurements)").fetchall()
            }
            assert after_second == after_first, "the second open changed the schema"
            rows_now = sorted(
                second.conn.execute(
                    "SELECT id, free_bytes FROM _measurements WHERE id LIKE 'old-%' OR id = 'new-1'"
                ).fetchall()
            )
            assert rows_now == rows_after_first, "the second open changed a row"
            assert second.get(_Measurement, "new-2").free_bytes == BIG
        finally:
            second.close()

    def test_a_column_the_model_does_not_call_an_int_is_left_alone(self, tmp_path):
        """This widens ONE specific mismatch, not every type in general. A
        VARCHAR the model now calls something else is a data decision, and this
        is not the place for one."""
        path = tmp_path / "other-types.duckdb"
        conn = duckdb.connect(str(path))
        conn.execute(
            "CREATE TABLE _measurements ("
            "  id VARCHAR PRIMARY KEY, free_bytes INTEGER, small VARCHAR"
            ")"
        )
        conn.execute("INSERT INTO _measurements VALUES ('old-1', 5, 'not a number')")
        conn.close()

        db = Database(path)
        try:
            db._ensure_table(_Measurement)
            # `free_bytes` widened; `small` is VARCHAR in the database and `int`
            # in the model, which is a real disagreement — but not this
            # mechanism's to resolve, and it must not be touched silently.
            assert _column_type(db.conn, "_measurements", "free_bytes") == "BIGINT"
            assert _column_type(db.conn, "_measurements", "small") == "VARCHAR"
        finally:
            db.close()


class TestTheRealLibrarySchema:
    """Every persisted model's `int` columns are BIGINT in a real library."""

    def test_no_registered_model_has_a_narrow_int_column(self, db):
        narrow = Database._NARROW_INT_TYPES
        offenders: list[str] = []
        for model in db._all_schema_models():
            table = db._table_name(model)
            try:
                rows = db.conn.execute(f'PRAGMA table_info("{table}")').fetchall()
            except Exception:
                continue
            types = {row[1]: str(row[2] or "").upper() for row in rows}
            for name, field_info in model.model_fields.items():
                if db._python_to_duckdb_type(field_info.annotation) != "BIGINT":
                    continue
                if types.get(name) in narrow:
                    offenders.append(f"{table}.{name} is {types[name]}")
        assert not offenders, (
            "these int columns still stop at 2,147,483,647:\n  " + "\n  ".join(offenders)
        )
