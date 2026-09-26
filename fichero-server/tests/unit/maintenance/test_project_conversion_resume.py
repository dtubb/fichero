"""Source-model slice 8b part 3 (#4924) — stopping, resuming, and the lock.

Spec: `segments-and-geometry.md`, "Converting a whole project: the rules" —
`source.convert.stops-starts-and-repeats-safely`, `.only-the-running-engine`,
`.the-machine-stays-usable`, and the "an edit gets ahead of the queue" rule.

The failure this file is about is NOT a slow conversion. It is a conversion that
half-succeeds and leaves a library in a state nobody chose. So the central test
is an EQUIVALENCE: an interrupted-then-resumed run must end up exactly where an
uninterrupted one would, row for row and id for id. Anything less and a
force-quit becomes a library in a third state that neither path would produce.

Every test builds its own temporary project.
"""

from __future__ import annotations

import pathlib
from datetime import timedelta
from types import SimpleNamespace

import pytest

# `db.storage_snapshots` cannot be imported before `db.storage` — they import
# each other, and snapshots-first raises. Importing storage here is what makes
# the `patch.object` below possible at all.
import fichero_server.db.storage  # noqa: F401
import fichero_server.db.storage_snapshots as snaps

from fichero_server.actions.registry import ActionContext, registry
from fichero_server.api.routes.document.segment_conversion import converted_pass_id
from fichero_server.db import Database
from fichero_server.maintenance import project_conversion as pc
from fichero_server.media.ocr_geometry import OCRGeometryBox, OCRGeometryResult
from fichero_server.models import (
    Artifact,
    DocType,
    Document,
    FileType,
    Segment,
    SegmentPass,
    Status,
)
from fichero_server.models.conversion import ConversionRun, ConversionVerdict

pytestmark = pytest.mark.source_model


@pytest.fixture
def project(tmp_path):
    package = tmp_path / "Resume.fichero"
    package.mkdir()
    db = Database(package / "library.duckdb")
    try:
        yield SimpleNamespace(db=db, path=package)
    finally:
        db.close()


def _pages(db, count: int) -> list[Document]:
    made: list[Document] = []
    for index in range(count):
        doc = Document(
            name=f"folio-{index:02d}.jpg", doc_type=DocType.file,
            file_type=FileType.image, path=f"/f/{index}.jpg", status=Status.completed,
        )
        db.save(doc)
        db.save(
            Artifact(
                document_id=doc.id, artifact_type="transcription", provider="qwen",
                ocr_geometry=OCRGeometryResult(
                    provider="qwen", text=f"line {index} a b",
                    boxes=[
                        OCRGeometryBox(
                            text=f"w{i}", bbox=[0.1, (i % 9) * 0.1, 0.2, 0.05],
                            level="line",
                        )
                        for i in range(2)
                    ],
                ),
            )
        )
        made.append(doc)
    return made


def _snapshot_stub(path: pathlib.Path, monkeypatch, *, snapshot_id: str = "snap") -> None:
    """Stub only the snapshot: it needs the APP database, which a temporary
    project has none of. Everything else in the runner is the real thing."""
    root = path / f"snapshots-{snapshot_id}"
    (root / "duckdb_export").mkdir(parents=True, exist_ok=True)
    stub = SimpleNamespace(
        id=snapshot_id, snapshot_path=str(root), duckdb_path="duckdb_export",
        is_pinned=False, duckdb_size_bytes=1, lance_size_bytes=0, files_size_bytes=0,
    )
    monkeypatch.setattr(snaps, "snapshot_library", lambda *_a, **_k: stub)
    monkeypatch.setattr(snaps, "_save_snapshot_record", lambda _r: None)
    monkeypatch.setattr(
        pc, "prove_snapshot", lambda *_a, **_k: {"tables": 1, "rows": 1, "mismatches": {}}
    )


def _state(db) -> dict:
    """Everything a caller could observe about the conversion's output, in a
    form two runs can be compared by — IDS INCLUDED, because "the same state"
    that allowed different ids would let a resumed run re-mint rows and still
    look equivalent."""
    return {
        "segments": sorted(
            (row.id, row.document_id, row.pass_id, row.kind, tuple(row.anchor.rect or []))
            for row in db.query(Segment)
        ),
        "passes": sorted(
            (row.id, row.document_id, row.provenance_kind.value)
            for row in db.query(SegmentPass)
        ),
        "markers": sorted(
            (row.id, row.geometry_superseded_by_pass_id) for row in db.query(Artifact)
        ),
    }


class TestStoppingAndResuming:
    """`source.convert.stops-starts-and-repeats-safely`."""

    def test_a_resumed_run_ends_exactly_where_an_uninterrupted_one_would(
        self, tmp_path, monkeypatch
    ):
        """THE CENTRAL TEST. Two projects, identical to begin with: one converted
        in a single pass, one stopped after two pages and resumed. Their final
        state must match row for row AND id for id.

        Ids are what makes this meaningful. `converted_segment_id` derives every
        id from its artifact and box position, so a resumed run cannot re-mint —
        and this is the test that would fail if that ever stopped being true.
        """
        straight_path = tmp_path / "Straight.fichero"
        stopped_path = tmp_path / "Stopped.fichero"
        straight_path.mkdir()
        stopped_path.mkdir()
        straight = Database(straight_path / "library.duckdb")
        stopped = Database(stopped_path / "library.duckdb")
        try:
            # The SAME artifact ids in both, so the derived segment ids are
            # comparable at all. Built by copying rows, not by luck.
            docs = _pages(straight, 5)
            for doc in docs:
                stopped.save(doc)
            for artifact in straight.query(Artifact):
                stopped.save(artifact)

            _snapshot_stub(straight_path, monkeypatch, snapshot_id="a")
            uninterrupted = pc.convert_project(straight, straight_path)
            assert uninterrupted.pages_converted == 5

            _snapshot_stub(stopped_path, monkeypatch, snapshot_id="b")
            seen = {"n": 0}

            def stop_after_two() -> bool:
                if seen["n"] >= 2:
                    return True
                seen["n"] += 1
                return False

            first_half = pc.convert_project(stopped, stopped_path, should_stop=stop_after_two)
            assert first_half.pages_converted == 2, "the stop must actually stop it"
            assert _state(stopped) != _state(straight), "half-done is not done"

            # A resumed run: the same call, no cursor, no argument saying where
            # to start. It asks the markers.
            second_half = pc.convert_project(stopped, stopped_path)
            assert second_half.pages_converted == 3

            assert _state(stopped) == _state(straight)
        finally:
            straight.close()
            stopped.close()

    def test_a_third_run_writes_nothing_and_files_no_report(
        self, project, monkeypatch
    ):
        _pages(project.db, 3)
        _snapshot_stub(project.path, monkeypatch)

        pc.convert_project(project.db, project.path)
        reports = len(project.db.query(ConversionRun))
        state = _state(project.db)

        assert pc.convert_project(project.db, project.path) is None
        assert pc.convert_project(project.db, project.path) is None

        assert len(project.db.query(ConversionRun)) == reports, "a no-op filed a report"
        assert _state(project.db) == state, "a no-op wrote something"

    def test_stopping_before_the_first_page_converts_nothing(self, project, monkeypatch):
        _pages(project.db, 3)
        _snapshot_stub(project.path, monkeypatch)

        run = pc.convert_project(project.db, project.path, should_stop=lambda: True)

        assert run.pages_converted == 0
        assert project.db.query(Segment) == []
        # And the project is untouched, so the next open starts from scratch.
        assert pc.conversion_scope(project.db) == (3, 3)

    def test_progress_survives_a_close_and_reopen(self, tmp_path, monkeypatch):
        """A quit is not a clean stop: the database is closed and reopened, and
        the runner has to work it out from the markers alone."""
        package = tmp_path / "Quit.fichero"
        package.mkdir()
        _snapshot_stub(package, monkeypatch)

        first = Database(package / "library.duckdb")
        try:
            _pages(first, 4)
            seen = {"n": 0}

            def stop_after_one() -> bool:
                if seen["n"] >= 1:
                    return True
                seen["n"] += 1
                return False

            pc.convert_project(first, package, should_stop=stop_after_one)
            converted_first = len(first.query(Segment))
        finally:
            first.close()

        second = Database(package / "library.duckdb")
        try:
            assert len(second.query(Segment)) == converted_first, "writes did not persist"
            run = pc.convert_project(second, package)
            assert run.pages_converted == 3
            assert pc.conversion_scope(second) == (0, 0)
        finally:
            second.close()


class TestTheLock:
    """`source.convert.only-the-running-engine` — one project, one runner."""

    def test_a_second_opening_is_refused_while_one_is_running(self, project):
        running = ConversionRun(
            verdict=ConversionVerdict.ready, heartbeat_at=pc.utc_now()
        )
        project.db.save(running)

        assert pc.running_conversion(project.db) is not None
        with pytest.raises(pc.ConversionAlreadyRunning) as excinfo:
            pc.convert_project(project.db, project.path)
        assert running.run_id in str(excinfo.value)

    def test_being_refused_is_not_mistaken_for_nothing_to_do(self, project, monkeypatch):
        """The two look identical from outside and mean opposite things, which is
        why one raises and the other returns None."""
        _pages(project.db, 2)
        project.db.save(
            ConversionRun(verdict=ConversionVerdict.ready, heartbeat_at=pc.utc_now())
        )
        _snapshot_stub(project.path, monkeypatch)

        with pytest.raises(pc.ConversionAlreadyRunning):
            pc.convert_project(project.db, project.path)
        # And nothing was converted, so the other runner's work is untouched.
        assert project.db.query(Segment) == []

    def test_a_finished_run_is_not_a_lock(self, project, monkeypatch):
        project.db.save(
            ConversionRun(
                verdict=ConversionVerdict.completed,
                heartbeat_at=pc.utc_now(), finished_at=pc.utc_now(),
            )
        )
        _pages(project.db, 1)
        _snapshot_stub(project.path, monkeypatch)

        assert pc.running_conversion(project.db) is None
        run = pc.convert_project(project.db, project.path)
        assert run.pages_converted == 1

    def test_a_refusal_verdict_is_not_a_lock(self, project, monkeypatch):
        """A run that refused for disk left no runner behind."""
        project.db.save(ConversionRun(verdict=ConversionVerdict.refused_disk))
        _pages(project.db, 1)
        _snapshot_stub(project.path, monkeypatch)

        assert pc.running_conversion(project.db) is None
        assert pc.convert_project(project.db, project.path).pages_converted == 1

    def test_an_abandoned_run_is_taken_over_not_obeyed_forever(
        self, project, monkeypatch
    ):
        """A force-quit must not wedge the project for good. The rules REQUIRE
        the next open to carry on, so a lock nobody can reclaim would contradict
        the design it protects."""
        stale = ConversionRun(
            verdict=ConversionVerdict.ready,
            heartbeat_at=pc.utc_now()
            - timedelta(seconds=pc.STALE_HEARTBEAT_SECONDS + 60),
        )
        project.db.save(stale)
        _pages(project.db, 2)
        _snapshot_stub(project.path, monkeypatch)

        assert pc.running_conversion(project.db) is None, "a stale claim is not a runner"
        assert [r.run_id for r in pc.abandoned_conversions(project.db)] == [stale.run_id]

        run = pc.convert_project(project.db, project.path)
        assert run.pages_converted == 2

        # The abandoned row STAYS, marked for what it was: "the app was killed
        # halfway through" is a fact about this library worth keeping.
        taken_over = project.db.get(ConversionRun, stale.id)
        assert taken_over.verdict is ConversionVerdict.failed
        assert taken_over.finished_at is not None
        assert any("took over" in f.reason for f in taken_over.failures)

    def test_the_heartbeat_advances_while_pages_convert(self, project, monkeypatch):
        _pages(project.db, 3)
        _snapshot_stub(project.path, monkeypatch)

        run = pc.convert_project(project.db, project.path)

        stored = project.db.get(ConversionRun, run.id)
        assert stored.heartbeat_at is not None
        assert stored.heartbeat_at >= stored.started_at


class TestAnEditGetsAheadOfTheQueue:
    """A page a person edits converts there and then, with the SAME ids the
    background work would have given it."""

    def test_a_page_edited_before_the_runner_reaches_it_is_skipped_not_redone(
        self, project, monkeypatch, client=None
    ):
        docs = _pages(project.db, 3)
        _snapshot_stub(project.path, monkeypatch)
        ahead = docs[2]
        artifact = project.db.query(Artifact, document_id=ahead.id)[0]

        # The edit's own conversion, through the same action a first edit uses.
        registry.invoke(
            project.db, "segment.convert_and_edit", {"document_id": ahead.id},
            ActionContext(actor="historian", is_bootstrap=True),
        )
        ids_after_edit = sorted(r.id for r in project.db.query(Segment))

        run = pc.convert_project(project.db, project.path)

        # The runner converted the other two and SKIPPED this one -- skipped, not
        # failed: somebody got there first, which is the design working.
        assert run.pages_converted == 2
        assert run.failures == []
        # And the ids the edit minted are still the ids that exist: the runner
        # did not re-mint or duplicate them.
        assert set(ids_after_edit) <= {r.id for r in project.db.query(Segment)}
        assert project.db.get(SegmentPass, converted_pass_id(artifact.id)) is not None

    def test_a_page_the_runner_already_did_is_not_converted_twice_by_an_edit(
        self, project, monkeypatch
    ):
        docs = _pages(project.db, 2)
        _snapshot_stub(project.path, monkeypatch)
        pc.convert_project(project.db, project.path)
        before = _state(project.db)

        # An edit arriving after the runner has been through: the page is already
        # rows, so the conversion branch has nothing left to do.
        from fichero_server.api.routes.document.segment_conversion import AlreadyConverted

        with pytest.raises((AlreadyConverted, Exception)):
            registry.invoke(
                project.db, "segment.convert_and_edit", {"document_id": docs[0].id},
                ActionContext(actor="historian", is_bootstrap=True),
            )
        assert _state(project.db) == before, "a second conversion changed something"
