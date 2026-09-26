"""Source-model slice 8b part 1 (#4924) — the preflight, before any page converts.

Spec: `segments-and-geometry.md`, "Converting a whole project: the rules";
`build-notes-readings-cascade-orders.md`, "Slice 8b" steps 1–3 and 5.

Behaviours pinned:
* `source.convert.starts-when-a-project-opens` (its "anything to do?" half) —
  nothing to convert writes NOTHING, not even a report row, which is what makes
  every later open free.
* `source.convert.refused-when-disk-is-short` — nothing starts, nothing is half
  done, the report carries the numbers, the next open tries again.
* `source.convert.snapshot-first-and-proved` — no snapshot, or one that fails
  the read-back, means no conversion. The snapshot is PROVED by opening it and
  counting, never by the writing call having returned.
* The report's home and its pin gate.

**Every test builds its own temporary project.** That rule is about the work,
not the feature: the finished feature converts real projects, and no test here
may ever touch one.

Nothing in this file converts a page — that is part 2. The point of shipping
preflight first is that the dangerous part cannot run until the safe part has
proved the snapshot.
"""

from __future__ import annotations

import pathlib
from types import SimpleNamespace

import pytest

from fichero_server.db import Database
from fichero_server.maintenance import project_conversion as pc
from fichero_server.media.ocr_geometry import OCRGeometryBox, OCRGeometryResult
from fichero_server.models import Artifact, DocType, Document, FileType, Status
from fichero_server.models.conversion import (
    ConversionFailure,
    ConversionRun,
    ConversionVerdict,
)

pytestmark = pytest.mark.source_model


@pytest.fixture
def project(tmp_path):
    """A temporary project, shaped like a real one: a package directory with a
    library database inside it."""
    package = tmp_path / "Temporary.fichero"
    package.mkdir()
    db = Database(package / "library.duckdb")
    try:
        yield SimpleNamespace(db=db, path=package)
    finally:
        db.close()


def _page_with_boxes(db, *, boxes: int = 2, artifact_type: str = "transcription") -> Artifact:
    doc = Document(
        name=f"page-{boxes}.jpg", doc_type=DocType.file, file_type=FileType.image,
        path=f"/p/{boxes}.jpg", status=Status.completed,
    )
    db.save(doc)
    artifact = Artifact(
        document_id=doc.id, artifact_type=artifact_type, provider="qwen",
        ocr_geometry=OCRGeometryResult(
            provider="qwen", text=" ".join(f"w{i}" for i in range(boxes)),
            boxes=[
                # The row WRAPS deliberately (`i % 9`): a straight line of
                # boxes walks off the page at i=9 (y=1.0, y+h=1.05) and
                # `OCRGeometryBox` rightly refuses it. These tests want ten or
                # more boxes to measure the disk estimate, and where the boxes
                # sit is irrelevant to that — so the fixture wraps rather than
                # the validator loosening. Do not "fix" this back into a line.
                OCRGeometryBox(
                    text=f"w{i}", bbox=[0.1, (i % 9) * 0.1, 0.2, 0.05], level="line"
                )
                for i in range(boxes)
            ],
        ),
    )
    db.save(artifact)
    return artifact


def _fake_snapshot(tmp_path, *, snapshot_id: str = "snap-1") -> SimpleNamespace:
    root = tmp_path / "snapshots" / snapshot_id
    (root / "duckdb_export").mkdir(parents=True)
    return SimpleNamespace(
        id=snapshot_id,
        snapshot_path=str(root),
        duckdb_path="duckdb_export",
        is_pinned=False,
        duckdb_size_bytes=1024,
        lance_size_bytes=0,
        files_size_bytes=0,
    )


def _export_every_table(db, snapshot, *, skip: str | None = None, corrupt: str | None = None):
    """Write the parquet export a real snapshot would, so `prove_snapshot` has
    something true to compare against — and so a test can make ONE table lie."""
    export = pathlib.Path(snapshot.snapshot_path) / "duckdb_export"
    for (table,) in db.conn.execute("SHOW TABLES").fetchall():
        if table == skip:
            continue
        out = export / f"{table}.parquet"
        if table == corrupt:
            # One row fewer than the project has: the shape of a snapshot that
            # was written while something else was still writing.
            db.conn.execute(
                f"COPY (SELECT * FROM \"{table}\" LIMIT 0) TO '{out}' (FORMAT parquet)"
            )
            continue
        db.conn.execute(f"COPY \"{table}\" TO '{out}' (FORMAT parquet)")


class TestIsThereAnythingToDo:
    """Step 1. One query over markers, and NO writes at all."""

    def test_an_empty_project_has_nothing_to_convert(self, project):
        assert pc.conversion_scope(project.db) == (0, 0)

    def test_nothing_to_do_writes_nothing_at_all(self, project):
        """Not even a report row. This is what makes every later open free."""
        assert pc.plan_conversion(project.db, project.path) is None
        assert project.db.query(ConversionRun) == []

    def test_a_result_with_boxes_and_no_marker_counts(self, project):
        _page_with_boxes(project.db, boxes=3)
        assert pc.conversion_scope(project.db) == (1, 1)

    def test_a_result_with_no_geometry_does_not_count(self, project):
        """`entities` and `grouping` artifacts have no boxes to convert."""
        doc = Document(
            name="p.jpg", doc_type=DocType.file, file_type=FileType.image,
            path="/p.jpg", status=Status.completed,
        )
        project.db.save(doc)
        project.db.save(Artifact(document_id=doc.id, artifact_type="entities", provider="q"))
        assert pc.conversion_scope(project.db) == (0, 0)

    def test_progress_is_the_marker_not_a_counter(self, project):
        """A converted result is one whose marker says so. Ask again after a
        crash and the answer is still right, which is why nothing stores a
        cursor."""
        artifact = _page_with_boxes(project.db)
        assert pc.conversion_scope(project.db) == (1, 1)

        project.db.save(
            artifact.model_copy(update={"geometry_superseded_by_pass_id": "pass-1"})
        )

        assert pc.conversion_scope(project.db) == (0, 0)
        assert pc.plan_conversion(project.db, project.path) is None

    def test_two_results_on_one_page_are_two_results_one_document(self, project):
        doc = Document(
            name="p.jpg", doc_type=DocType.file, file_type=FileType.image,
            path="/p.jpg", status=Status.completed,
        )
        project.db.save(doc)
        for kind in ("transcription", "translation"):
            project.db.save(
                Artifact(
                    document_id=doc.id, artifact_type=kind, provider="q",
                    ocr_geometry=OCRGeometryResult(
                        provider="q", text="a",
                        boxes=[OCRGeometryBox(text="a", bbox=[0.1, 0.1, 0.2, 0.05], level="line")],
                    ),
                )
            )
        assert pc.conversion_scope(project.db) == (2, 1)


class TestWillItFit:
    """Step 2. Refused when the disk is short — with the numbers."""

    def test_a_short_disk_refuses_and_reports_the_numbers(self, project, monkeypatch):
        _page_with_boxes(project.db, boxes=5)
        monkeypatch.setattr(
            pc.shutil, "disk_usage",
            lambda _p: SimpleNamespace(total=1, used=1, free=1),
        )

        run = pc.plan_conversion(project.db, project.path)

        assert run is not None
        assert run.verdict is ConversionVerdict.refused_disk
        assert run.disk_required_bytes and run.disk_required_bytes > run.disk_available_bytes
        assert run.disk_available_bytes == 1
        assert run.results_to_convert == 1
        # Nothing was half done: no snapshot was even attempted.
        assert run.snapshot_id is None
        assert run.finished_at is not None

    def test_the_estimate_grows_with_the_work(self, project):
        before, _ = pc.estimate_space(project.db, project.path)
        _page_with_boxes(project.db, boxes=200)
        after, _ = pc.estimate_space(project.db, project.path)
        assert after > before, "more boxes must need more room"

    def test_the_margin_is_applied(self, project, monkeypatch):
        """"With room to spare" is a number, not a sentiment."""
        monkeypatch.setattr(pc, "DISK_MARGIN", 1.0)
        _page_with_boxes(project.db, boxes=10)
        tight, _ = pc.estimate_space(project.db, project.path)
        monkeypatch.setattr(pc, "DISK_MARGIN", 4.0)
        generous, _ = pc.estimate_space(project.db, project.path)
        assert generous > tight

    def test_an_unreadable_disk_raises_rather_than_assuming_room(
        self, project, monkeypatch
    ):
        def boom(_path):
            raise OSError("no such device")

        monkeypatch.setattr(pc.shutil, "disk_usage", boom)
        with pytest.raises(pc.ConversionPreflightFailed):
            pc.estimate_space(project.db, project.path)


class TestIsThereAWayBack:
    """Step 3. The snapshot is PROVED by reading it back, table by table."""

    def test_a_faithful_snapshot_proves_clean(self, project, tmp_path):
        _page_with_boxes(project.db)
        snapshot = _fake_snapshot(tmp_path)
        _export_every_table(project.db, snapshot)

        proof = pc.prove_snapshot(project.db, snapshot)

        assert proof["mismatches"] == {}
        assert proof["tables"] > 0
        assert proof["rows"] > 0, "a project with a page in it exports rows"

    def test_a_snapshot_with_a_wrong_row_count_is_caught(self, project, tmp_path):
        """The shape of a snapshot written while something else was writing."""
        _page_with_boxes(project.db)
        snapshot = _fake_snapshot(tmp_path)
        _export_every_table(project.db, snapshot, corrupt="artifacts")

        proof = pc.prove_snapshot(project.db, snapshot)

        assert "artifacts" in proof["mismatches"]
        assert proof["mismatches"]["artifacts"]["expected"] > 0
        assert proof["mismatches"]["artifacts"]["found"] == 0

    def test_a_missing_table_export_is_caught_unless_the_table_is_empty(
        self, project, tmp_path
    ):
        _page_with_boxes(project.db)
        snapshot = _fake_snapshot(tmp_path)
        _export_every_table(project.db, snapshot, skip="artifacts")

        proof = pc.prove_snapshot(project.db, snapshot)
        assert proof["mismatches"]["artifacts"]["found"] == "no parquet file"

    def test_no_exports_at_all_is_caught(self, project, tmp_path):
        _page_with_boxes(project.db)
        snapshot = _fake_snapshot(tmp_path)
        # A snapshot record pointing at a directory with nothing in it.
        proof = pc.prove_snapshot(project.db, snapshot)
        assert proof["mismatches"], "an empty export must not prove clean"

    def test_a_project_reporting_no_tables_is_blindness_not_cleanliness(
        self, project, monkeypatch
    ):
        """The property the swallowed index failure lacked: a check that cannot
        see must fail, not pass."""
        class _Blind:
            """A connection that answers everything with nothing.

            `close` is not decoration: without it the `db` fixture's teardown
            raises `AttributeError` and this test ERRORS instead of asserting,
            so a test whose entire point is "blindness must not read as
            cleanliness" would itself have been passing through a blind spot.
            Found by running it (#5056 review).
            """

            def execute(self, *_a, **_k):
                return SimpleNamespace(fetchall=lambda: [], fetchone=lambda: None)

            def close(self) -> None:
                pass

        monkeypatch.setattr(project.db, "conn", _Blind())
        with pytest.raises(pc.ConversionPreflightFailed):
            pc._live_row_counts(project.db)

    def test_a_failed_snapshot_refuses_and_converts_nothing(
        self, project, monkeypatch, tmp_path
    ):
        _page_with_boxes(project.db)

        def boom(*_a, **_k):
            raise RuntimeError("DuckDB export failed")

        monkeypatch.setattr(
            "fichero_server.db.storage_snapshots.snapshot_library", boom
        )
        run = pc.plan_conversion(project.db, project.path)

        assert run is not None
        assert run.verdict is ConversionVerdict.refused_snapshot
        assert "DuckDB export failed" in str(run.snapshot_proof)
        assert run.finished_at is not None

    def test_a_snapshot_that_does_not_read_back_refuses(
        self, project, monkeypatch, tmp_path
    ):
        _page_with_boxes(project.db)
        snapshot = _fake_snapshot(tmp_path, snapshot_id="snap-bad")
        _export_every_table(project.db, snapshot, corrupt="documents")
        monkeypatch.setattr(
            "fichero_server.db.storage_snapshots.snapshot_library",
            lambda *_a, **_k: snapshot,
        )

        run = pc.plan_conversion(project.db, project.path)

        assert run.verdict is ConversionVerdict.refused_snapshot
        assert "documents" in run.snapshot_proof["mismatches"]
        # The snapshot is still named, so a person can look at what was taken.
        assert run.snapshot_id == "snap-bad"

    def test_a_proved_snapshot_is_pinned_and_the_run_is_ready(
        self, project, monkeypatch, tmp_path
    ):
        _page_with_boxes(project.db)
        snapshot = _fake_snapshot(tmp_path, snapshot_id="snap-good")
        _export_every_table(project.db, snapshot)
        monkeypatch.setattr(
            "fichero_server.db.storage_snapshots.snapshot_library",
            lambda *_a, **_k: snapshot,
        )
        saved: list = []
        monkeypatch.setattr(
            "fichero_server.db.storage_snapshots._save_snapshot_record",
            lambda record: saved.append(record),
        )

        run = pc.plan_conversion(project.db, project.path)

        assert run.verdict is ConversionVerdict.ready
        assert run.snapshot_id == "snap-good"
        assert run.snapshot_proof["mismatches"] == {}
        # Pinned through the flag that `_enforce_retention` already honours --
        # not a second retention mechanism.
        assert snapshot.is_pinned is True
        assert saved and saved[0] is snapshot

    def test_a_pin_that_cannot_be_written_does_not_refuse_the_conversion(
        self, project, monkeypatch, tmp_path
    ):
        """Refusing over bookkeeping would be refusing over the wrong thing:
        the snapshot exists and is proved, which is the actual safety net."""
        _page_with_boxes(project.db)
        snapshot = _fake_snapshot(tmp_path, snapshot_id="snap-unpinnable")
        _export_every_table(project.db, snapshot)
        monkeypatch.setattr(
            "fichero_server.db.storage_snapshots.snapshot_library",
            lambda *_a, **_k: snapshot,
        )

        def boom(_record):
            raise RuntimeError("app database is read-only")

        monkeypatch.setattr(
            "fichero_server.db.storage_snapshots._save_snapshot_record", boom
        )

        run = pc.plan_conversion(project.db, project.path)
        assert run.verdict is ConversionVerdict.ready
        assert run.snapshot_id == "snap-unpinnable"


class TestTheReport:
    """Its own table in the library's own database, and its pin gate."""

    def test_the_report_has_its_table_when_the_library_opens(self, project):
        tables = {
            r[0] for r in project.db.conn.execute(
                "SELECT table_name FROM duckdb_tables()"
            ).fetchall()
        }
        assert "conversionruns" in tables

    def test_a_report_round_trips_with_its_failures(self, project):
        run = ConversionRun(
            verdict=ConversionVerdict.completed,
            results_to_convert=3, documents_to_convert=2,
            pages_converted=1, pages_skipped=1,
            failures=[
                ConversionFailure(
                    document_id="doc-1", artifact_id="art-1",
                    reason="boxes could not become segments: overlapping ids",
                )
            ],
            seconds=12.5,
        )
        project.db.save(run)

        stored = project.db.get(ConversionRun, run.id)
        assert stored.verdict is ConversionVerdict.completed
        assert stored.pages_converted == 1
        assert len(stored.failures) == 1
        assert stored.failures[0].document_id == "doc-1"
        assert stored.seconds == pytest.approx(12.5)

    def test_the_snapshot_stays_pinned_until_the_run_is_finished_and_seen(self):
        """The way back from a conversion nobody has looked at yet must not be
        tidied away by a retention rule."""
        run = ConversionRun(verdict=ConversionVerdict.ready, snapshot_id="s1")
        assert run.snapshot_may_be_unpinned is False

        run.finished_at = pc.utc_now()
        assert run.snapshot_may_be_unpinned is False, "finished is not seen"

        run.seen_at = pc.utc_now()
        assert run.snapshot_may_be_unpinned is True
