"""A tester's library is healed by the product, not by us (#4666).

Daniel, on the RTF escapes found in a real library: "do we do this by hand or
in the app? like for Javier? we want it to work properly."

So the repair is not a script someone runs over a beta tester's data. It is a
migration action with the same three properties every destructive product
action needs — you can see what it WOULD do before it does it, it records what
it changed, and you can put it back. This pins all three against rows shaped
like the real ones.

Verified live against a clone of Daniel's Caciques library on 2026-09-04:
4 claims corrupt → dry run wrote nothing → apply repaired 6 rows → rollback
restored all 6 and the corruption count returned exactly to 4.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.integration._seedlib import seed

from fichero_server.db import db_manager
from fichero_server.db.migrations.runner import MigrationRunner, MigrationStatus
from fichero_server.models import Artifact, DocType, Document
from fichero_server.models.knowledge import KnowledgeClaim

#: Both shapes: RTF writes `\'f1`, and what reached the graph was the bare
#: `'f1` inside a word, the backslash lost on the way.
ESCAPE = re.compile(r"(?:\\'|(?<=[^\W\d_])')[0-9a-fA-F]{2}(?=[^\W\d_])")

RTF_SOURCE = (
    "{\\rtf1\\ansi\\ansicpg1252\n"
    "\\pard\\pardirnatural\\partightenfactor0\n"
    "\\f0\\fs24 \\cf0 Andres Varela ca\\'f1istin\\\n}"
)


@pytest.fixture
def library(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("FICHERO_SKIP_DEFAULT_WORKFLOWS", "1")
    path = tmp_path / "healed.fichero"
    seed(path)
    db = db_manager.get_database(path)
    db.save(Document(id="d1", name="533r", doc_type=DocType.page))
    db.save(
        KnowledgeClaim(
            id="c1",
            text="Andres ca'f1istin estantes en nuestro se'f1or.",
            source_document_id="d1",
            predicate_verb="ca'f1istin",
            object_phrase="estantes en nuestro se'f1or",
        )
    )
    # An artifact that IS an RTF document — the shape the first live run
    # rewrote in place, repairing a display bug by corrupting the source.
    db.save(
        Artifact(id="a1", document_id="d1", artifact_type="transcription", content=RTF_SOURCE)
    )
    return db


def _corrupt_claims(db) -> int:
    return sum(1 for c in db.all(KnowledgeClaim) if ESCAPE.search(c.text or ""))


class TestYouCanSeeWhatItWouldDo:
    def test_a_dry_run_reports_and_writes_nothing(self, library):
        before = _corrupt_claims(library)
        assert before == 1

        result = MigrationRunner(library).repair_rtf_escapes(dry_run=True)
        assert result.status is MigrationStatus.completed
        assert result.migrated >= 1
        assert result.dry_run is True
        assert _corrupt_claims(library) == before, "a dry run wrote to the library"


class TestItRecordsWhatItChanged:
    def test_every_change_is_logged_with_its_before_state(self, library):
        from fichero_server.models.knowledge import MutationLog

        result = MigrationRunner(library).repair_rtf_escapes()
        assert _corrupt_claims(library) == 0

        logs = [
            m
            for m in library.all(MutationLog)
            if m.run_id == result.details["run_id"]
        ]
        assert logs, "a repair with no audit trail cannot be undone"
        for entry in logs:
            assert entry.before_state and entry.after_state
            assert entry.changed_fields


class TestYouCanPutItBack:
    def test_rollback_restores_the_rows_exactly(self, library):
        runner = MigrationRunner(library)
        before = _corrupt_claims(library)

        applied = runner.repair_rtf_escapes()
        runner.save_run_result(applied)
        assert _corrupt_claims(library) == 0

        rolled = runner.rollback(applied.details["run_id"])
        assert rolled.status is MigrationStatus.rolled_back
        assert rolled.failed == 0
        assert _corrupt_claims(library) == before, "undo did not put the rows back"


class TestItDoesNotBreakWhatItTouches:
    def test_an_rtf_document_is_left_alone(self, library):
        # Decoding escapes inside `{\rtf...}` rewrites valid cp1252 markup into
        # something no RTF reader can decode — repairing a display bug by
        # corrupting the document behind it. Caught on the first live run.
        MigrationRunner(library).repair_rtf_escapes()
        assert library.get(Artifact, "a1").content == RTF_SOURCE

    def test_running_it_twice_changes_nothing_the_second_time(self, library):
        runner = MigrationRunner(library)
        assert runner.repair_rtf_escapes().migrated >= 1
        again = runner.repair_rtf_escapes()
        assert again.migrated == 0
        assert again.details.get("reason")
