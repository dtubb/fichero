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


class TestAnIndexBlocksTheWideningAndThatIsReported:
    """The path where the original bug SURVIVES on a real library, and the only
    one #5059 left resting on a comment rather than a test.

    DuckDB refuses `ALTER COLUMN … TYPE BIGINT` when an index depends on the
    column: "Cannot change the type of this column: an index depends on it!".
    `_widen_int_columns` catches that narrowly and warns, on the reasoning that a
    library which cannot be widened is a library that still works exactly as it
    did — refusing to OPEN it over a column that has held every value it ever
    needed would be worse than the ceiling.

    That reasoning is right, and it is also how the original defect stays alive:
    an index-blocked column keeps its INT32 ceiling, and the only signal is a log
    line. Two such columns are known and named in the source — `references.year`
    and `canvas_layout.z_index` — and the comment beside them says, correctly,
    that they are NOT a precedent: the obstacle (an index) and the exemption (a
    value that cannot overflow) coincided by chance. Had the index sat on a
    genuine byte count, the bug would have remained on a real library.

    So these tests pin the three things that claim depends on:
      * the widening is refused, not crashed through
      * the library still opens and every row survives
      * values within INT32 still round-trip, so "it works as it did" is true

    What they deliberately do NOT assert is that a large value now saves — it
    does not, and cannot, until the index is dropped and recreated. A test
    claiming otherwise would paper over exactly the residue this describes.
    """

    def _old_library_with_an_index(self, path) -> None:
        conn = duckdb.connect(str(path))
        conn.execute(
            "CREATE TABLE _measurements ("
            "  id VARCHAR PRIMARY KEY, free_bytes INTEGER, small INTEGER"
            ")"
        )
        conn.execute("CREATE INDEX idx_measurements_free ON _measurements(free_bytes)")
        conn.execute("INSERT INTO _measurements VALUES ('old-1', 1024, 7)")
        assert _column_type(conn, "_measurements", "free_bytes") == "INTEGER"
        conn.close()

    def test_the_library_still_opens_and_saves(self, tmp_path):
        """"It still works exactly as it did" is the whole justification for
        swallowing the refusal, so it is the thing to check."""
        path = tmp_path / "indexed.duckdb"
        self._old_library_with_an_index(path)

        db = Database(path)
        try:
            db.save(_Measurement(id="new-1", free_bytes=2048, small=9))
            assert db.get(_Measurement, "new-1").free_bytes == 2048
            assert db.get(_Measurement, "old-1").free_bytes == 1024
        finally:
            db.close()

    def test_an_index_blocks_the_WHOLE_TABLE_not_just_the_indexed_column(self, tmp_path):
        """The refusal is per TABLE, and `_widen_int_columns`' docstring says per column.

        Measured against DuckDB directly: altering the indexed column raises
        `CatalogException: Cannot change the type of this column: an index depends
        on it!`, and then altering ANY OTHER column of the same table raises
        `DependencyException: Cannot alter entry "t" because there are entries
        that depend on it` — an error about the table, not about the column. So an
        index on one column freezes the integer width of every column beside it.

        This matters more than the wording: the source's exemption reasoning is
        "this particular column cannot overflow", and the real question is whether
        any int column on an INDEXED TABLE can. `free_bytes` here is exactly the
        case the source comment warned about and believed it had avoided — a
        genuine byte count, frozen at INT32, because something unrelated to it
        has an index.

        If this ever reads BIGINT, DuckDB learned to alter an indexed table and
        the warning path became dead code that should be removed — a good outcome,
        but one somebody must notice rather than inherit.
        """
        path = tmp_path / "indexed-type.duckdb"
        self._old_library_with_an_index(path)

        db = Database(path)
        try:
            db.save(_Measurement(id="new-1", free_bytes=2048))
            assert _column_type(db.conn, "_measurements", "free_bytes") == "INTEGER"
            # `small` carries no index of its own and is still not widened.
            assert _column_type(db.conn, "_measurements", "small") == "INTEGER"
        finally:
            db.close()

    def test_the_refusal_is_reported_and_names_the_column(self, tmp_path, caplog):
        """A silent skip would be #5070's shape exactly — an operation that did
        not happen while everything reported fine. The column name is what makes
        the warning actionable rather than noise."""
        import logging

        path = tmp_path / "indexed-log.duckdb"
        self._old_library_with_an_index(path)

        db = Database(path)
        try:
            with caplog.at_level(logging.WARNING, logger="fichero_server.db"):
                db.save(_Measurement(id="new-1", free_bytes=2048))
            warnings = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
            blocked = [m for m in warnings if "free_bytes" in m and "BIGINT" in m]
            assert blocked, f"no warning named the un-widened column; got {warnings}"
        finally:
            db.close()

    def test_a_large_value_is_still_refused_on_the_indexed_column(self, tmp_path):
        """The residue, stated as a test rather than as a comment.

        This is the assertion that keeps #5059 honest: on a pre-existing library
        whose narrow column carries an index, the ceiling is STILL THERE. If a
        future index-blocked column holds a genuine byte count, this is the
        failure its users will get — so the fix for that case is to drop the
        index, alter, and recreate it, not to widen the exemption.
        """
        path = tmp_path / "indexed-big.duckdb"
        self._old_library_with_an_index(path)

        db = Database(path)
        try:
            with pytest.raises(Exception) as raised:
                db.save(_Measurement(id="too-big", free_bytes=REAL_FAILING_VALUE))
            assert "INT32" in str(raised.value) or "out of range" in str(raised.value), raised.value
        finally:
            db.close()


#: Every `int` column that an index leaves at INT32 on a library created before
#: #5059. Measured on a fresh library by crossing `duckdb_indexes()` with the
#: BIGINT columns in `duckdb_columns()`, not by reading source comments — the
#: source names two of these six.
INDEX_BLOCKED_INT_COLUMNS = {
    # Named in `_widen_int_columns` and judged: a publication year and a layout
    # stacking order are inherently bounded.
    "references.year",
    "canvas_layout.z_index",
    # NOT named there, and so never judged until now. All four are revision or
    # ordering counters: a segment would have to be edited two billion times, and
    # a forwarding chain reach two billion hops. Bounded in practice, and that is
    # a judgement someone should be able to see rather than infer.
    "segments.version",
    "segmentversions.version",
    "readingorderentrys.version",
    "segmentforwardings.sequence",
}


def test_the_engine_skips_exactly_the_judged_columns():
    """#5191: the engine no longer ATTEMPTS these (the ALTER always failed and warned at every
    open). Its list must be the measured one, or a column that can overflow would be skipped."""
    from fichero_server.db import Database

    assert Database.JUDGED_NARROW_INT_COLUMNS == INDEX_BLOCKED_INT_COLUMNS


class TestTheExemptionListIsCompleteAndJudged:
    """The residue of #5059, pinned so a seventh exemption cannot arrive silently.

    The fix's own comment says an index-blocked column "must be judged on whether
    ITS values can exceed 2,147,483,647" rather than waved through — and then
    provides no mechanism for that judging to happen. The only signal is a log
    warning at library open, and warnings are not read.

    So this measures the set from the database and compares it to a written list.
    A new index on a table with an int column makes this test fail, which is the
    moment to ask whether that column can overflow. That is the whole point: the
    question gets asked by a failing test rather than by somebody noticing a line
    in a log.
    """

    def _blocked(self, db) -> set[str]:
        indexed = {
            row[0]
            for row in db.conn.execute("SELECT DISTINCT table_name FROM duckdb_indexes()").fetchall()
        }
        return {
            f"{table}.{column}"
            for table, column in db.conn.execute(
                "SELECT table_name, column_name FROM duckdb_columns() WHERE data_type = 'BIGINT'"
            ).fetchall()
            if table in indexed
        }

    def test_the_blocked_set_is_exactly_the_judged_list(self, tmp_path):
        """A failure here is not a bug to silence: it is a column to judge.

        If the new entry can hold bytes, microseconds, or a row count from a large
        archive, the fix is to drop the index, ALTER, and recreate it — verifying
        the recreate. If it cannot, add it here with the reason it cannot, the way
        the six above say why.
        """
        db = Database(tmp_path / "fresh.duckdb")
        try:
            blocked = self._blocked(db)
        finally:
            db.close()
        assert blocked == INDEX_BLOCKED_INT_COLUMNS, (
            "index-blocked int columns changed.\n"
            f"  new (judge these): {sorted(blocked - INDEX_BLOCKED_INT_COLUMNS)}\n"
            f"  gone (drop these): {sorted(INDEX_BLOCKED_INT_COLUMNS - blocked)}"
        )

    def test_each_blocked_column_is_a_counter_or_a_bounded_ordinal(self, tmp_path):
        """A cheap shape check on the judgement, so the list cannot fill with byte counts.

        Every name here ends in `version`, `year`, `sequence` or `index`. A column
        called `*_bytes`, `*_size`, `*_micros` or `*_count` arriving in this set is
        the case the source comment feared and must not be waved through on the
        strength of the six that came before it.
        """
        for qualified in INDEX_BLOCKED_INT_COLUMNS:
            column = qualified.split(".", 1)[1]
            assert column.endswith(("version", "year", "sequence", "index")), (
                f"{qualified} is not obviously a bounded counter — judge it explicitly"
            )
            for danger in ("bytes", "size", "micros", "millis", "nanos", "count", "offset"):
                assert danger not in column, (
                    f"{qualified} looks like it can grow past INT32; an index must not "
                    "be the reason it keeps a 32-bit ceiling"
                )
