"""#4414 Stage 4: run the REAL Catalogue preset through the REAL runner.

Every other catalogue test drives ``build_graph(...).ainvoke(state)``. That
exercises the graph, but it skips ``execution/runner.py`` entirely — and the
runner is what the app actually calls. Everything the run RECORDS (as opposed
to writes) lives there: the run row, the snapshot, the timeline, and the
resolved scope.

That gap hid a live defect. ``resolve_run_scope`` had tests. Persisting a
scope through ``ActivityStore`` had tests. The line joining them read the
selection out of the wrong ``state`` — the run *registry* entry
(``{workflow_id, workflow_name, status, events, error, final_state}``), not
the graph state, which is not built until two hundred lines later. So the
resolver was handed ``None`` on every run and every run recorded an empty
scope while appearing to record one. Two green unit tests either side of a
seam that was never joined.

Which is the #4414 thesis exactly: what a component does is not what the
configured thing does, and only running the configured thing can tell them
apart.

Nothing here is stubbed except the model. The preset JSON is the shipped one,
all twelve of its nodes execute, the DB is real, and the run goes through
``_run_workflow_in_background``.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from tests.integration._seedlib import seed
from tests.unit.workflows.test_default_workflow_e2e_harness import (
    FIXTURE_TEXT,
    _install_deterministic_workflow_stubs,
)

from fichero_server.api.routes.workflow_execution.schemas import (
    ExecuteWorkflowRequest,
)
from fichero_server.db import db_manager
from fichero_server.execution import runner
from fichero_server.models import Artifact, DocType, Document, FileType, Workflow
from fichero_server.workflows.activity import get_activity_tracker
from fichero_server.workflows.default_workflows import _load_preset_files
from fichero_server.workflows.selection import SelectionKind, WorkflowSelection

import fichero_server.workflows.tools  # noqa: F401


def _catalogue_workflow() -> Workflow:
    """The shipped Catalogue preset as the STORED model.

    Deliberately not the harness's ``_load_catalogue_workflow`` — that returns
    a ``WorkflowDef`` (a graph-runtime projection), and the runner is handed
    the stored ``Workflow`` whose nodes are plain dicts. Passing the runtime
    shape here would test a call the app never makes.
    """
    preset = next(p for p in _load_preset_files() if p["name"] == "Catalogue")
    return Workflow(
        id="default-catalogue-real-preset-run",
        name=preset["name"],
        description=preset.get("description", ""),
        nodes=preset["nodes"],
        edges=preset["edges"],
        config=preset.get("config", {}),
        folder_path=preset.get("folder_path", "/"),
    )


@pytest.fixture(autouse=True)
def _no_seeding(monkeypatch):
    monkeypatch.setenv("FICHERO_SKIP_DEFAULT_WORKFLOWS", "1")


@pytest.fixture
def two_folder_library(tmp_path: Path):
    """Two sibling folders, one document each. Only the first is selected."""
    library_path = tmp_path / "real-preset.fichero"
    seed(library_path)
    db = db_manager.get_database(library_path)

    for folder_id, name, doc_id, filename in (
        ("caja-3", "Caja 3", "caja-3-doc", "caja3.txt"),
        ("caja-4", "Caja 4", "caja-4-doc", "caja4.txt"),
    ):
        db.save(Document(id=folder_id, name=name, doc_type=DocType.folder))
        source = tmp_path / filename
        source.write_text(FIXTURE_TEXT, encoding="utf-8")
        db.save(
            Document(
                id=doc_id,
                parent_id=folder_id,
                name=filename,
                path=str(source),
                doc_type=DocType.file,
                file_type=FileType.text,
                page_content=FIXTURE_TEXT,
                metadata={"transcription": FIXTURE_TEXT},
            )
        )
    return library_path, db


def _run_through_the_runner(
    library_path: Path,
    thread_id: str,
    selection: WorkflowSelection,
):
    """Drive the real background runner, as ``POST /execute`` does."""
    workflow = _catalogue_workflow()
    runner._set_workflow_state(
        thread_id,
        {
            "workflow_id": workflow.id,
            "workflow_name": workflow.name,
            "status": "accepted",
            "events": runner.WorkflowEventHub(),
            "error": None,
            "final_state": None,
        },
    )
    request = ExecuteWorkflowRequest(
        workflow_id=workflow.id,
        inputs={},
        thread_id=thread_id,
        selection=selection,
        skip_cache=True,
    )
    db = db_manager.get_database(library_path)
    try:
        asyncio.run(
            runner._run_workflow_in_background(thread_id, workflow, request, db)
        )
    finally:
        runner._remove_workflow_state(thread_id)


def _stored_run(library_path: Path, thread_id: str):
    db = db_manager.get_database(library_path)
    tracker = get_activity_tracker(str(db.path))
    return asyncio.run(tracker.store.get_workflow_run(thread_id))


class TestTheRunRecordsWhatItWasScopedTo:
    """#4384/#4396. The assertion that catches an over-scoped run on sight."""

    def test_a_folder_run_records_the_folders_descendants(
        self, two_folder_library, monkeypatch
    ):
        _install_deterministic_workflow_stubs(monkeypatch)
        library_path, _db = two_folder_library

        _run_through_the_runner(
            library_path,
            "real-preset-scope",
            WorkflowSelection(kind=SelectionKind.folder, ids=["caja-3"]),
        )

        run = _stored_run(library_path, "real-preset-scope")
        assert run is not None, "the runner persisted no run row at all"
        assert run.resolved_scope, (
            "the run recorded no scope. Activity cannot report what a run "
            "operated on (#4384) and an over-scoped run stays invisible until "
            "its effects reach the data (#4396)"
        )
        assert run.resolved_scope["requested_ids"] == ["caja-3"]
        assert run.resolved_scope["resolved_ids"] == ["caja-3-doc"]
        assert run.resolved_scope["resolved_count"] == 1

    def test_the_recorded_scope_never_names_the_sibling_folder(
        self, two_folder_library, monkeypatch
    ):
        """A record that agreed with an over-scoped run would corroborate the
        defect instead of exposing it."""
        _install_deterministic_workflow_stubs(monkeypatch)
        library_path, _db = two_folder_library

        _run_through_the_runner(
            library_path,
            "real-preset-scope-sibling",
            WorkflowSelection(kind=SelectionKind.folder, ids=["caja-3"]),
        )

        scope = _stored_run(library_path, "real-preset-scope-sibling").resolved_scope
        # Precondition. An empty scope excludes the sibling too, and would
        # satisfy the check below while describing nothing — which is exactly
        # the state this file was written to catch.
        assert scope and scope["resolved_ids"], (
            "the recorded scope is empty, so 'the sibling is absent' is true "
            "of a record that names nothing at all"
        )
        assert "caja-4" not in scope["resolved_ids"]
        assert "caja-4-doc" not in scope["resolved_ids"]

    def test_the_record_keeps_the_kind_the_client_claimed(
        self, two_folder_library, monkeypatch
    ):
        """`kinds` says what the ids turned out to BE; `requested_kind` says
        what the request CLAIMED. A client asserting `folder` while sending a
        document list is only legible when both are kept."""
        _install_deterministic_workflow_stubs(monkeypatch)
        library_path, _db = two_folder_library

        _run_through_the_runner(
            library_path,
            "real-preset-kind",
            WorkflowSelection(kind=SelectionKind.documents, ids=["caja-3-doc"]),
        )

        scope = _stored_run(library_path, "real-preset-kind").resolved_scope
        assert scope is not None
        assert scope["requested_kind"] == "documents"
        assert scope["kinds"] == {"caja-3-doc": "file"}


class TestTheShippedPresetsOwnNodesRun:
    """The six folder-cleanup nodes and citations_extract used to be replaced
    with no-ops by the shared harness — seven of the preset's twelve nodes. A
    harness that swaps out over half the shipped preset proves nothing about
    the shipped preset."""

    def test_folder_cleanup_writes_its_canonical_lists_to_the_folder(
        self, two_folder_library, monkeypatch
    ):
        _install_deterministic_workflow_stubs(monkeypatch)
        library_path, db = two_folder_library

        _run_through_the_runner(
            library_path,
            "real-preset-cleanup",
            WorkflowSelection(kind=SelectionKind.folder, ids=["caja-3"]),
        )

        clean_types = {
            a.artifact_type
            for a in db.all(Artifact)
            if a.document_id == "caja-3" and a.artifact_type.endswith("_clean")
        }
        assert clean_types, (
            "no `<type>_clean` artifact reached the folder document — the "
            "folder-cleanup nodes did not run, or their output went somewhere "
            "other than the folder they describe (#4404/#4414)"
        )
        assert {"people_clean", "places_clean"} <= clean_types, (
            f"only {sorted(clean_types)} landed; the fixture names a person "
            "and a place, so both cleanup nodes had work to do"
        )

    def test_no_cleanup_output_reaches_the_unselected_folder(
        self, two_folder_library, monkeypatch
    ):
        _install_deterministic_workflow_stubs(monkeypatch)
        library_path, db = two_folder_library

        _run_through_the_runner(
            library_path,
            "real-preset-cleanup-isolation",
            WorkflowSelection(kind=SelectionKind.folder, ids=["caja-3"]),
        )

        artifacts = db.all(Artifact)
        # Precondition: a run that produced nothing touches nothing, and would
        # pass the isolation check below without ever having run.
        assert [a for a in artifacts if a.document_id in {"caja-3", "caja-3-doc"}], (
            "the run wrote no artifacts anywhere, so 'nothing reached Caja 4' "
            "is vacuous"
        )
        stray = sorted(
            a.artifact_type
            for a in artifacts
            if a.document_id in {"caja-4", "caja-4-doc"}
        )
        assert stray == [], (
            f"a run scoped to Caja 3 wrote {stray} onto Caja 4 (#4396)"
        )
