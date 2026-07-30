"""A run must record what it was scoped to (#4384 #4396 #4397).

`workflow_runs` recorded which workflow executed and when, but never what it
executed ON. Two live consequences:

* **#4384 is unbuildable.** Activity cannot report a run's scope because
  nothing persisted it — no UI work fixes that.
* **#4396 stayed invisible.** A client sent a whole folder when the user had
  picked one file. The run did exactly as asked, recorded nothing about the
  ask, and the over-scoping was found by noticing catalogue output on the
  wrong documents rather than by anything in the system objecting.

The stored record is the SERVER's resolved set alongside the requested ids,
because the discrepancy between them is the defect. A row reading
`Catalogue · 47 files` next to a run the user started on one PDF is wrong on
its face — that is the cheapest possible detection for the whole class.

Nothing here skips.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path

import pytest

from tests.integration._seedlib import seed

from fichero_server.db import db_manager
from fichero_server.models import DocType, Document, FileType
from fichero_server.workflows.activity_store import ActivityStore
from fichero_server.workflows.run_scope import resolve_run_scope


@pytest.fixture(autouse=True)
def _no_seeding(monkeypatch):
    monkeypatch.setenv("FICHERO_SKIP_DEFAULT_WORKFLOWS", "1")


@pytest.fixture
def library(tmp_path: Path):
    """A folder holding one 3-page PDF and one loose text file."""
    package = tmp_path / "scope.fichero"
    seed(package)
    db = db_manager.get_database(package)

    folder = Document(id="sc-folder", name="Caja 3", doc_type=DocType.folder)
    db.save(folder)

    pdf = Document(
        id="sc-pdf", parent_id=folder.id, name="marshall.pdf",
        doc_type=DocType.file, file_type=FileType.pdf, path=str(tmp_path / "m.pdf"),
    )
    db.save(pdf)
    for page in range(1, 4):
        db.save(Document(
            id=f"sc-page-{page}", parent_id=pdf.id, name=f"page {page}",
            doc_type=DocType.page, sequence=page,
        ))

    db.save(Document(
        id="sc-loose", parent_id=folder.id, name="note.txt",
        doc_type=DocType.file, file_type=FileType.text, path=str(tmp_path / "n.txt"),
    ))

    # A sibling folder that must never appear in any scope below.
    other = Document(id="sc-other-folder", name="Caja 4", doc_type=DocType.folder)
    db.save(other)
    db.save(Document(
        id="sc-outsider", parent_id=other.id, name="outside.txt",
        doc_type=DocType.file, file_type=FileType.text, path=str(tmp_path / "o.txt"),
    ))
    return package, db


class TestScopeResolution:
    def test_a_folder_resolves_to_its_leaf_descendants(self, library):
        _package, db = library
        scope = resolve_run_scope(db, ["sc-folder"])

        assert scope["requested_ids"] == ["sc-folder"]
        assert sorted(scope["resolved_ids"]) == [
            "sc-loose", "sc-page-1", "sc-page-2", "sc-page-3",
        ]
        assert scope["resolved_count"] == 4
        assert scope["kinds"] == {"sc-folder": "folder"}

    def test_a_pdf_resolves_to_its_pages_not_itself(self, library):
        """The unit of work is the page — recording the parent would misstate
        how much the run actually touched."""
        _package, db = library
        scope = resolve_run_scope(db, ["sc-pdf"])
        assert sorted(scope["resolved_ids"]) == [
            "sc-page-1", "sc-page-2", "sc-page-3",
        ]

    def test_a_leaf_resolves_to_itself(self, library):
        _package, db = library
        assert resolve_run_scope(db, ["sc-loose"])["resolved_ids"] == ["sc-loose"]

    def test_nothing_outside_the_selection_is_ever_included(self, library):
        """The #4396 assertion, stated directly."""
        _package, db = library
        scope = resolve_run_scope(db, ["sc-pdf"])
        assert "sc-outsider" not in scope["resolved_ids"]
        assert "sc-loose" not in scope["resolved_ids"]

    def test_the_discrepancy_is_visible(self, library):
        """What makes #4396 detectable: one requested id, four resolved. A row
        reading `1 selected → 4 documents` is inspectable; a row with no scope
        at all is not."""
        _package, db = library
        scope = resolve_run_scope(db, ["sc-folder"])
        assert scope["requested_count"] == 1
        assert scope["resolved_count"] == 4


class TestScopeResolutionIsHonest:
    def test_an_empty_selection_records_an_empty_scope(self, library):
        _package, db = library
        scope = resolve_run_scope(db, [])
        assert scope["requested_count"] == 0
        assert scope["resolved_count"] == 0

    def test_an_unknown_id_does_not_invent_a_document(self, library):
        _package, db = library
        scope = resolve_run_scope(db, ["does-not-exist"])
        assert scope["requested_ids"] == ["does-not-exist"]
        assert scope["resolved_ids"] == []

    def test_a_duplicate_selection_is_counted_once(self, library):
        _package, db = library
        scope = resolve_run_scope(db, ["sc-pdf", "sc-pdf"])
        assert sorted(scope["resolved_ids"]) == [
            "sc-page-1", "sc-page-2", "sc-page-3",
        ]

    def test_a_resolution_failure_says_so_rather_than_reporting_empty(self):
        """An unexplained empty scope reads as 'the run touched nothing',
        which is a different and much more alarming claim than 'we could not
        work out what it touched'."""

        class ExplodingDB:
            def get(self, *_a, **_k):
                raise RuntimeError("db is gone")

            def query(self, *_a, **_k):
                return []

        scope = resolve_run_scope(ExplodingDB(), ["sc-folder"])
        assert scope["resolved_count"] == 0
        assert "db is gone" in scope["resolution_error"]


class TestScopeIsPersistedAndReadBack:
    def test_a_saved_run_round_trips_its_scope(self, library, tmp_path: Path):
        package, db = library
        store = ActivityStore(str(package / "fichero.duckdb"))
        scope = resolve_run_scope(db, ["sc-folder"])

        asyncio.run(store.save_workflow_run(
            thread_id="scope-run-1",
            workflow_id="wf-catalogue",
            workflow_name="Catalogue",
            started_at=datetime.now(timezone.utc),
            resolved_scope=scope,
        ))
        run = asyncio.run(store.get_workflow_run("scope-run-1"))

        assert run is not None
        assert run.resolved_scope is not None, (
            "the run recorded no scope — #4384 cannot be built and #4396 stays "
            "invisible"
        )
        assert run.resolved_scope["resolved_count"] == 4
        assert sorted(run.resolved_scope["resolved_ids"]) == [
            "sc-loose", "sc-page-1", "sc-page-2", "sc-page-3",
        ]

    def test_a_run_saved_without_scope_reads_back_as_none(self, library, tmp_path: Path):
        """Rows written before the column existed must still load — real
        libraries have them, and they are not regenerated."""
        package, _db = library
        store = ActivityStore(str(package / "fichero.duckdb"))
        asyncio.run(store.save_workflow_run(
            thread_id="legacy-run",
            workflow_id="wf",
            workflow_name="Old",
            started_at=datetime.now(timezone.utc),
        ))
        run = asyncio.run(store.get_workflow_run("legacy-run"))
        assert run is not None
        assert run.resolved_scope is None
