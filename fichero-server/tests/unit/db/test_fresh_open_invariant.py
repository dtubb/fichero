"""Guard 1 (#5056): what a library MUST have the moment it opens.

Spec: `source.store.bounded-reads` for the indexes; the schema-on-open ruling
recorded in `build-notes-identity-and-storage.md` ("schema on open, data on
first edit, never a side effect of a GET") for the tables.

WHY THIS GUARD EXISTS. On 2026-09-26, three tables slice 8 reads once per page
were missing from `Database._all_schema_models`. The consequence was not an
error — a missing table reads back empty — it was that the index migration,
which runs AT OPEN, found no table to index. It logged a warning and carried
on. So `idx_segmentpasschoices_document_id` was never built on a library's
first open, `idx_contentrepresentations_segment_id` could not be built at all
because the column it names had not been reconciled yet, and every derived page
text was a table scan per line. Nothing was red. Nothing could be, because the
only thing that knew had written a warning to a log nobody reads.

That is a vacuous guard: not a check that gave a wrong answer, but a check that
reported success while seeing nothing. This file is the check that could not.

**So this guard asserts against the CATALOG, never against the migration's
return value, because the migration's own report of success is the thing that
cannot be trusted.** That sentence is the whole lesson of the missing indexes,
and it is here rather than in a commit message because the next person tempted
to "simplify" this by checking what `migrate_segment_indices` returned needs to
meet it first. The same reasoning picks `duckdb_indexes()` over the DDL list's
labels, and parses each DDL rather than trusting its label: the DDL is what the
database is actually told, so it is the only description that cannot drift from
what exists. Check the artefact the system actually consumes, not the intention
upstream of it.

WHAT IT DELIBERATELY DOES NOT DO. It does not try to work out which models
*ought* to be registered — that census is heuristic, needs an allowlist nobody
can justify yet, and is #5056's deferred second half. This guard is purely
declarative: whatever the code DECLARES it will create, it must actually have
created by the time a library is open. Declarations in, reality out, no
judgement in between.
"""

from __future__ import annotations

import itertools
import re

import pytest

from fichero_server.db import Database
from fichero_server.db.migrations.schema import SEGMENT_INDEX_STATEMENTS

pytestmark = pytest.mark.source_model


class SchemaReadFailed(RuntimeError):
    """The guard could not read the schema.

    Raised rather than returning an empty set, because "I found no tables" and
    "there are no tables" are the same value and opposite facts. A guard that
    cannot read its input has gone BLIND, and must fail — the whole reason this
    file exists is a check that passed while seeing nothing.
    """


def _names(db: Database, query: str, what: str) -> set[str]:
    try:
        rows = db.conn.execute(query).fetchall()
    except Exception as exc:  # pragma: no cover - only on a broken connection
        raise SchemaReadFailed(f"could not read {what}: {exc}") from exc
    if not rows:
        raise SchemaReadFailed(
            f"read {what} and got NOTHING. A fresh library has dozens; an empty "
            "answer means this guard is blind, not that the library is clean."
        )
    return {row[0] for row in rows}


@pytest.fixture
def fresh(tmp_path):
    """A library opened once, through the real `Database`, and nothing else.

    No saves, no routes, no fixtures that write. Everything asserted below must
    be true of OPENING a library, which is the promise being guarded.
    """
    db = Database(tmp_path / "fresh.duckdb")
    try:
        yield db
    finally:
        db.close()


class TestEveryRegisteredModelHasItsTableAtOpen:
    """`_all_schema_models` is a DECLARATION. This is the check that it is kept.

    A model in that tuple is one the code says will have a table from the
    moment a library opens — so that an open-time migration can index it, a
    seed can fill it, and its new columns arrive on open rather than on
    whatever write happens first.
    """

    def test_no_registered_model_is_missing_its_table(self, fresh):
        tables = _names(
            fresh, "SELECT table_name FROM duckdb_tables()", "duckdb_tables()"
        )
        declared = {
            model.__name__: fresh._table_name(model)
            for model in fresh._all_schema_models()
        }
        missing = sorted(
            f"{name} -> {table}"
            for name, table in declared.items()
            if table not in tables
        )
        assert not missing, (
            "these registered models have no table after a library opens, so "
            "anything that runs at open and needs them sees nothing:\n  "
            + "\n  ".join(missing)
        )

    def test_the_declaration_is_not_empty(self, fresh):
        """The guard must not pass because it compared nothing to nothing."""
        assert len(list(fresh._all_schema_models())) > 40


#: What each declaration actually creates, read out of its DDL.
#:
#: The entry's first element is a LABEL, and it is not always the object's
#: name: `seq_segment_forwarding` declares a sequence called
#: `segment_forwarding_seq`. Found by running this guard rather than by reading
#: the list, which is the argument for parsing the DDL — the DDL is what the
#: database is actually told, so it is the only description that cannot drift
#: from what exists. The list also mixes KINDS: nineteen indexes and one
#: sequence, which live in different catalogs.
_CREATES = re.compile(
    r"CREATE\s+(INDEX|SEQUENCE)\s+IF\s+NOT\s+EXISTS\s+([A-Za-z_][A-Za-z0-9_]*)",
    re.IGNORECASE,
)

#: Which catalog answers for each kind.
_CATALOG = {
    "INDEX": ("SELECT index_name FROM duckdb_indexes()", "duckdb_indexes()"),
    "SEQUENCE": ("SELECT sequence_name FROM duckdb_sequences()", "duckdb_sequences()"),
}


def _declared_objects() -> list[tuple[str, str, str, str]]:
    """``(kind, object_name, label, what it serves)`` for every declaration.

    Raises when a DDL cannot be parsed: a statement whose kind this guard does
    not understand is one it cannot check, and silently skipping it is how a
    guard comes to cover less than it appears to.
    """
    out: list[tuple[str, str, str, str]] = []
    for entry in SEGMENT_INDEX_STATEMENTS:
        label, ddl, serves = entry
        match = _CREATES.search(ddl)
        if match is None:
            raise SchemaReadFailed(
                f"{label}: cannot tell what this DDL creates, so it cannot be "
                f"guarded — teach `_CREATES` about it rather than skipping it: {ddl!r}"
            )
        out.append((match.group(1).upper(), match.group(2), label, serves))
    return out


class TestEveryDeclaredObjectExistsAtOpen:
    """The three-stacked-failures case, caught at its first link.

    `migrate_segment_indices` builds each statement inside its own try/except,
    so a failure is a log line and nothing more. This asserts against the
    DECLARATIONS rather than restating them, so adding an index to that list is
    all anyone has to do for it to be guarded.
    """

    def test_nothing_declared_is_missing(self, fresh):
        missing: list[str] = []
        for kind, group in itertools.groupby(
            sorted(_declared_objects()), key=lambda row: row[0]
        ):
            query, what = _CATALOG[kind]
            existing = _names(fresh, query, what)
            missing += [
                f"{kind.lower()} {obj} ({label}): {serves}"
                for _k, obj, label, serves in group
                if obj not in existing
            ]
        assert not missing, (
            "these are declared but were not created when the library opened — "
            "the query each one serves is a table scan until somebody "
            "notices:\n  " + "\n  ".join(missing)
        )

    def test_every_declaration_is_well_formed(self):
        """A declaration that cannot be checked is worse than none."""
        assert SEGMENT_INDEX_STATEMENTS, "the declaration list is empty"
        seen_labels: set[str] = set()
        seen_objects: set[str] = set()
        for kind, obj, label, serves in _declared_objects():
            assert kind in _CATALOG, f"{label}: no catalog knows about {kind}"
            assert label not in seen_labels, f"{label} is declared twice"
            assert obj not in seen_objects, f"{obj} is created twice"
            seen_labels.add(label)
            seen_objects.add(obj)
            assert serves.strip(), f"{label}: no reason given"

    def test_the_declarations_cover_both_kinds_the_guard_understands(self):
        """If the sequence ever leaves this list, the SEQUENCE branch above
        stops being exercised and would rot untested. Asserting the shape keeps
        the guard's own coverage honest."""
        kinds = {kind for kind, _o, _l, _s in _declared_objects()}
        assert kinds == {"INDEX", "SEQUENCE"}, kinds

    def test_opening_twice_keeps_every_declared_index(self, tmp_path):
        """Slice 8's actual bug was an index that appeared only on the SECOND
        open — the table it indexed was created mid-iteration, after the
        migration had already run. A first-open-only assertion would have
        caught it; this pins that a reopen neither loses nor is needed."""
        path = tmp_path / "twice.duckdb"
        declared = {obj for kind, obj, _l, _s in _declared_objects() if kind == "INDEX"}
        query, what = _CATALOG["INDEX"]

        first = Database(path)
        try:
            after_first = _names(first, query, what)
        finally:
            first.close()

        second = Database(path)
        try:
            after_second = _names(second, query, what)
        finally:
            second.close()

        assert declared <= after_first, sorted(declared - after_first)
        assert declared <= after_second, sorted(declared - after_second)


class TestTheGuardFailsWhenItCannotSee:
    """A guard must fail when it cannot read its input, never pass vacuously.

    This is the property the swallowed index failure lacked, so it is asserted
    directly rather than assumed of the helper.
    """

    def test_an_unreadable_schema_raises_rather_than_returning_empty(self, fresh):
        with pytest.raises(SchemaReadFailed):
            _names(fresh, "SELECT table_name FROM duckdb_tables() WHERE false", "nothing")

    def test_a_broken_connection_raises(self, fresh):
        with pytest.raises(SchemaReadFailed):
            _names(fresh, "SELECT this_is_not_valid_sql FROM nowhere", "bad sql")
