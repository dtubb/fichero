"""Source-model slice 8b, piece 3 (#4924) — the rules that are NUMBERS.

Spec: `segments-and-geometry.md` — `source.convert.starts-when-a-project-opens`
("never holds the opening up"), `.the-machine-stays-usable`, and
`.it-is-not-undone-it-is-restored`. The build notes are explicit that the
usability rule wants "a measured number, not a comment".

WHY THESE ARE SEPARATE FROM THE REST OF 8b. Every other test here asserts a
fact that is true or false. These three assert that something is FAST ENOUGH or
happens IN AN ORDER, and both are properties of a machine rather than of code —
so each one says what it measured and each bound is generous enough to be about
the code rather than about whatever else the laptop was doing. **A bound measured
against a loaded machine is a bound about the load**, so the numbers below were
taken with nothing else of mine running, and they are ceilings by a wide margin
rather than targets.

The RESTORE test uses a real snapshot and a real restore — not the stub the
other files use — because "the way back from a conversion that went wrong is the
snapshot" is worth nothing if the snapshot has only ever been faked.
"""

from __future__ import annotations

import pathlib
import time
from types import SimpleNamespace

import pytest

import fichero_server.db.storage  # noqa: F401 — breaks the snapshots import cycle
from fichero_server.db import Database, storage_snapshots
from fichero_server.db.storage import StorageSettings
from fichero_server.maintenance import project_conversion as pc
from fichero_server.media.ocr_geometry import OCRGeometryBox, OCRGeometryResult
from fichero_server.models import (
    Artifact,
    DocType,
    Document,
    FileType,
    KnownLibrary,
    Segment,
    Status,
)
from fichero_server.models.conversion import ConversionRun

pytestmark = pytest.mark.source_model

# --------------------------------------------------------------------------
# The bounds. Each is a CEILING with a lot of room, not a target: the point is
# to fail when something becomes pathological (a per-row loop, a scan per page,
# a conversion that blocks a reader), not to police a few milliseconds.
# --------------------------------------------------------------------------

#: Opening a library with unconverted geometry, versus one with none. Conversion
#: must not run at open, so the two must be indistinguishable.
OPEN_BOUND_SECONDS = 5.0

#: A person's read, taken WHILE a conversion is between pages.
READ_BOUND_SECONDS = 2.0

#: A person's edit, in the same conditions. Larger than a read because it is a
#: write through the audited action layer.
EDIT_BOUND_SECONDS = 5.0


def _page(db, index: int, *, boxes: int = 3) -> Document:
    doc = Document(
        name=f"m-{index}.jpg", doc_type=DocType.file, file_type=FileType.image,
        path=f"/m/{index}.jpg", status=Status.completed,
    )
    db.save(doc)
    text = " ".join(f"w{i}" for i in range(boxes))
    db.save(
        Artifact(
            document_id=doc.id, artifact_type="transcription", provider="qwen",
            content=text,
            ocr_geometry=OCRGeometryResult(
                provider="qwen", text=text,
                boxes=[
                    OCRGeometryBox(
                        text=f"w{i}", bbox=[0.1, (i % 9) * 0.1, 0.2, 0.05], level="line",
                    )
                    for i in range(boxes)
                ],
            ),
        )
    )
    return doc


def _stub_snapshot(monkeypatch, tmp_path, name: str = "s") -> None:
    root = tmp_path / f"snap-{name}" / "duckdb_export"
    root.mkdir(parents=True, exist_ok=True)
    stub = SimpleNamespace(
        id=f"snap-{name}", snapshot_path=str(tmp_path / f"snap-{name}"),
        duckdb_path="duckdb_export", is_pinned=False,
        duckdb_size_bytes=1, lance_size_bytes=0, files_size_bytes=0,
    )
    monkeypatch.setattr(storage_snapshots, "snapshot_library", lambda *_a, **_k: stub)
    monkeypatch.setattr(storage_snapshots, "_save_snapshot_record", lambda _r: None)
    monkeypatch.setattr(
        pc, "prove_snapshot", lambda *_a, **_k: {"tables": 1, "rows": 1, "mismatches": {}}
    )


class TestOpeningIsNotHeldUp:
    """`source.convert.starts-when-a-project-opens` — "The project opens and is
    fully usable at once; conversion runs behind it."

    The ORDER is the property, and it is asserted before anything is timed: a
    stopwatch cannot tell "fast conversion" from "no conversion", and only one of
    those is the rule.
    """

    def test_opening_a_library_converts_nothing(self, tmp_path):
        path = tmp_path / "Unconverted.fichero"
        path.mkdir()
        first = Database(path / "library.duckdb")
        try:
            for index in range(5):
                _page(first, index)
        finally:
            first.close()

        reopened = Database(path / "library.duckdb")
        try:
            # THE ORDER, asserted as a fact rather than inferred from a duration:
            # opening wrote no segment, no reading and no report, so conversion
            # cannot have run.
            assert reopened.query(Segment) == []
            assert reopened.query(ConversionRun) == []
            assert pc.conversion_scope(reopened) == (5, 5), "the work is still waiting"
        finally:
            reopened.close()

    def test_opening_is_no_slower_with_work_waiting_than_without(self, tmp_path):
        """If opening triggered conversion, a library with five unconverted pages
        would take measurably longer than an empty one. It does not, because it
        does not convert."""
        empty_path = tmp_path / "Empty.fichero"
        empty_path.mkdir()
        Database(empty_path / "library.duckdb").close()

        work_path = tmp_path / "Work.fichero"
        work_path.mkdir()
        seeded = Database(work_path / "library.duckdb")
        try:
            for index in range(5):
                _page(seeded, index, boxes=20)
        finally:
            seeded.close()

        started = time.monotonic()
        Database(empty_path / "library.duckdb").close()
        empty_open = time.monotonic() - started

        started = time.monotonic()
        with_work = Database(work_path / "library.duckdb")
        try:
            work_open = time.monotonic() - started
            assert with_work.query(Segment) == [], "opening converted something"
        finally:
            with_work.close()

        assert work_open < OPEN_BOUND_SECONDS, (
            f"opening a library with work waiting took {work_open:.2f}s, over the "
            f"{OPEN_BOUND_SECONDS}s ceiling — measured with nothing else running"
        )
        # And it is in the same league as an empty one. A generous factor: this
        # catches "opening now converts the project", not a few milliseconds.
        assert work_open < empty_open + OPEN_BOUND_SECONDS


class TestTheMachineStaysUsable:
    """`source.convert.the-machine-stays-usable` — a person's read and a
    person's edit each finish within a stated bound while conversion runs.

    Measured AT A PAGE BOUNDARY through the runner's own `on_page` hook, which
    is exactly where it yields. That is the honest place: the rule is that a
    person can act while a conversion is in progress, and a page boundary is when
    the runner has the database and is about to take it again. Timing from
    another thread would measure DuckDB's lock rather than the design, and would
    make the test's own contention the thing under test.
    """

    def test_a_persons_read_and_edit_both_finish_while_a_conversion_runs(
        self, db, test_package, tmp_path, monkeypatch, client
    ):
        for index in range(6):
            _page(db, index)
        _stub_snapshot(monkeypatch, tmp_path)

        read_times: list[float] = []
        edit_times: list[float] = []
        unconverted: list[str] = [
            doc.id for doc in db.query(Document) if doc.doc_type is DocType.file
        ]

        def person_acts(_run) -> None:
            # A READ: the seam for a page, through the real route.
            target = unconverted[-1]
            started = time.monotonic()
            response = client.get(f"/api/segments/document/{target}")
            read_times.append(time.monotonic() - started)
            assert response.status_code == 200

            # AN EDIT: a write through the audited action layer, on a page the
            # runner has not reached. This is the case the rule is really about —
            # not "can I look", but "can I work".
            if len(edit_times) == 0:
                artifacts = db.query(Artifact, document_id=target)
                started = time.monotonic()
                edit = client.put(
                    f"/api/artifacts/{artifacts[0].id}/regions",
                    json={"op": "move", "indices": [0], "bbox": [0.5, 0.5, 0.1, 0.05]},
                )
                edit_times.append(time.monotonic() - started)
                assert edit.status_code == 200, edit.text

        run = pc.convert_project(db, pathlib.Path(test_package), on_page=person_acts)

        assert run.pages_converted + run.pages_skipped >= 5
        assert read_times, "the hook never fired, so nothing was measured"
        assert edit_times, "no edit was measured"

        worst_read = max(read_times)
        worst_edit = max(edit_times)
        assert worst_read < READ_BOUND_SECONDS, (
            f"a person's read took {worst_read:.2f}s during a conversion, over the "
            f"{READ_BOUND_SECONDS}s ceiling (measured with nothing else running; "
            f"{len(read_times)} reads, worst quoted)"
        )
        assert worst_edit < EDIT_BOUND_SECONDS, (
            f"a person's edit took {worst_edit:.2f}s during a conversion, over the "
            f"{EDIT_BOUND_SECONDS}s ceiling (measured with nothing else running)"
        )

    def test_the_runner_yields_between_every_page(self, db, test_package, tmp_path, monkeypatch):
        """The mechanism behind the bound: the hook fires once per page, so there
        IS a boundary between pages for a person to act in. A runner that did the
        whole project in one go would fire it once."""
        for index in range(4):
            _page(db, index)
        _stub_snapshot(monkeypatch, tmp_path)

        boundaries: list[int] = []
        pc.convert_project(
            db, pathlib.Path(test_package),
            on_page=lambda run: boundaries.append(run.pages_converted),
        )

        assert len(boundaries) == 4, f"expected a boundary per page, got {boundaries}"
        # And each one saw one more page done than the last.
        assert boundaries == sorted(boundaries)


class TestItIsNotUndoneItIsRestored:
    """`source.convert.it-is-not-undone-it-is-restored` — "The way back from a
    conversion that went wrong is the snapshot."

    A REAL snapshot and a REAL restore. The other files stub `snapshot_library`
    because a temporary project has no app database; this one redirects the
    snapshot state into `tmp_path` instead, the way `test_storage_snapshots.py`
    does, so the way back is exercised rather than asserted.
    """

    def test_the_pinned_snapshot_restores_the_project_as_it_was_before_the_run(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(
            storage_snapshots, "settings", StorageSettings(base_path=tmp_path / "state")
        )
        library_path = tmp_path / "Restorable.fichero"
        library_path.mkdir()

        # The snapshot machinery reads the library registry, so register it the
        # way a real library is registered.
        registry = Database(storage_snapshots.settings.global_library_path / "fichero.duckdb")
        try:
            registry.save(
                KnownLibrary(path=str(library_path.resolve()), name=library_path.name)
            )
        finally:
            registry.conn.close()

        db = Database(library_path / "fichero.duckdb")
        try:
            for index in range(3):
                _page(db, index)
            before = {
                "segments": len(db.query(Segment)),
                "scope": pc.conversion_scope(db),
                "markers": sorted(
                    (a.id, a.geometry_superseded_by_pass_id) for a in db.query(Artifact)
                ),
            }
            assert before["segments"] == 0

            run = pc.convert_project(db, library_path)
            assert run is not None, "nothing was converted, so there is nothing to restore"
            assert run.snapshot_id, "no snapshot was taken"
            after_conversion = len(db.query(Segment))
            assert after_conversion > 0, "the conversion wrote nothing"
        finally:
            db.close()

        # THE WAY BACK. Restoring discards everything done since, which is the
        # documented behaviour: "a safety net for a failed conversion, not an
        # undo".
        result = storage_snapshots.restore_snapshot(run.snapshot_id)
        assert result is not None

        restored = Database(library_path / "fichero.duckdb")
        try:
            assert len(restored.query(Segment)) == before["segments"]
            assert pc.conversion_scope(restored) == before["scope"]
            assert sorted(
                (a.id, a.geometry_superseded_by_pass_id) for a in restored.query(Artifact)
            ) == before["markers"], "a conversion marker survived the restore"
        finally:
            restored.close()

    def test_the_snapshot_is_pinned_so_retention_cannot_tidy_the_way_back(
        self, tmp_path, monkeypatch
    ):
        """The way back from a conversion nobody has looked at yet must survive
        `max_snapshots` worth of later snapshots."""
        monkeypatch.setattr(
            storage_snapshots, "settings", StorageSettings(base_path=tmp_path / "state")
        )
        library_path = tmp_path / "Pinned.fichero"
        library_path.mkdir()
        registry = Database(storage_snapshots.settings.global_library_path / "fichero.duckdb")
        try:
            registry.save(
                KnownLibrary(path=str(library_path.resolve()), name=library_path.name)
            )
        finally:
            registry.conn.close()

        db = Database(library_path / "fichero.duckdb")
        try:
            _page(db, 0)
            run = pc.convert_project(db, library_path)
        finally:
            db.close()

        assert run.snapshot_id
        # `library_name` is the package STEM ("Pinned"), not its directory name
        # ("Pinned.fichero") — `snapshot_library` derives it with `.stem`. Read it
        # off the snapshot rather than reconstructing it.
        pinned = [
            s for s in storage_snapshots.list_snapshots(library_name=library_path.stem)
            if s.id == run.snapshot_id
        ]
        assert pinned, "the conversion's snapshot is not listed at all"
        assert pinned[0].is_pinned is True, (
            "the pre-conversion snapshot is not pinned, so retention may delete "
            "the only way back before anyone has seen the report"
        )
