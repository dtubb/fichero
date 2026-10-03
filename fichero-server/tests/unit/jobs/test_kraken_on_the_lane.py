"""Kraken pages run as jobs on the local-model lane (#5358, `activity.lane.*`).

Spec: docs/contributor_manual/specs/ui/activity-and-automatic-work.md -- `activity.lane.group-by-model`,
`activity.lane.load-once`, `activity.kraken-mlx-inference-visible`; ai/local-runtimes.md section 3.

The maintainer's goal is Kraken running efficiently: one reader loaded and used for a whole
folder, one heavy model at a time, and the network half of a page (a vision model reading the
lines Kraken found) never holding the lane. These tests drive the real Transcribe tool and the
real scheduler thread; only Kraken itself is faked (no torch, no model download).
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import threading
from pathlib import Path

import pytest

from fichero_server.db.manager import db_manager
from fichero_server.execution import jobs


def _png(path: Path) -> Path:
    from PIL import Image

    Image.new("RGB", (16, 16), (255, 255, 255)).save(str(path), format="PNG")
    return path


def _geometry(text: str = "vecino de la ciudad"):
    from fichero_server.media.ocr_geometry import OCRGeometryBox, OCRGeometryLevel, OCRGeometryResult

    return OCRGeometryResult(
        text=text, provider="kraken", model="kraken-mccatmus", source="kraken-htr",
        boxes=[OCRGeometryBox(text=text, bbox=[0.1, 0.1, 0.8, 0.05], level=OCRGeometryLevel.LINE,
                              provider="kraken", model="kraken-mccatmus", source="kraken-htr",
                              char_start=0, char_end=len(text),
                              metadata={"baseline_px": [[100.0, 300.0], [900.0, 300.0]]})],
    )


async def _transcribe(library_path: str, doc, extra: dict):
    from fichero_server.llm import LLMConfig
    from fichero_server.workflows.tools.sources import files_tool
    from fichero_server.workflows.tools.transcribe import transcribe

    src = await files_tool(inputs={}, state={"selected_doc_ids": [doc.id], "library_path": library_path},
                           llm_config=LLMConfig(provider="", model=""))
    return await transcribe(
        inputs={"files": src["files"], "documents": src["documents"], "vision_mode": "kraken",
                "regions_first": False, **extra},
        state={"library_path": library_path, "task_id": None},
        llm_config=LLMConfig(provider="", model=""),
    )


def _page(db, tmp_path):
    from fichero_server.models import DocType, Document, FileType

    doc = Document(name="hand.png", doc_type=DocType.file, file_type=FileType.image,
                   path=str(_png(tmp_path / "hand.png")))
    db.save(doc)
    return doc


def _rows(db):
    """The Kraken rows (a saved page also queues its embed, which is not what these pin)."""
    return db.execute_fetchall("SELECT kind, subject, model, state, reason FROM jobs "
                               "WHERE kind IN ('find-lines', 'read-a-line') ORDER BY created_at")


class TestAWorkflowsKrakenPageIsAJob:
    @pytest.mark.asyncio
    async def test_a_kraken_reading_runs_on_the_lane_named_by_its_reader(self, test_package, tmp_path, monkeypatch):
        """WHY: a Kraken page that bypassed the lane could load a second heavy model beside the
        embedder, and would not be grouped with the folder's other pages. The model is named by
        the reader, so a folder read with one reader keeps it loaded."""
        import fichero_server.llm.kraken_runtime as kraken_runtime

        library = str(test_package)
        db = db_manager.get_database(library)
        doc = _page(db, tmp_path)
        threads = []

        def fake_recognize(image_path, model_path, *, model_id=None, rendition_id=None, home=None):
            threads.append(threading.current_thread().name)
            return _geometry()

        monkeypatch.setattr(kraken_runtime, "recognize_to_geometry", fake_recognize)
        monkeypatch.setattr(kraken_runtime, "resolve_recognition_model",
                            lambda ref: ("/models/mccatmus.mlmodel", "kraken-mccatmus"))
        result = await _transcribe(library, doc, {"kraken_model": "kraken-mccatmus"})

        assert not result.get("error"), result.get("error")
        assert threads == ["fichero-jobs"]
        assert _rows(db) == [("read-a-line", doc.id, "kraken:kraken-mccatmus", "done", None)]

    @pytest.mark.asyncio
    async def test_the_vision_model_reading_kraken_lines_does_not_hold_the_lane(self, test_package, tmp_path, monkeypatch):
        """WHY: with `lines_read_by="model"` a vision model reads each line Kraken found, a
        network wait of seconds a page. If that wait held the lane, every other page and the
        embedder would queue behind the network. Here the line reader itself puts work on the
        lane and waits for it: that only finishes if the lane is free."""
        import fichero_server.llm.kraken_runtime as kraken_runtime
        import fichero_server.llm.line_reader as line_reader

        library = str(test_package)
        db = db_manager.get_database(library)
        doc = _page(db, tmp_path)
        monkeypatch.setattr(kraken_runtime, "segment_to_geometry",
                            lambda image_path, rendition_id=None: _geometry(""))
        ran_beside = []

        async def fake_read_lines(image_path, geometry, config, language=None):
            ran_beside.append(await asyncio.wait_for(jobs.run_on_lane(
                library, "find-lines", "other-page", model="kraken:blla", fn=lambda: "other page"), 10))
            return _geometry("read by a model")

        monkeypatch.setattr(line_reader, "read_lines", fake_read_lines)
        result = await _transcribe(library, doc, {"lines_read_by": "model"})

        assert not result.get("error"), result.get("error")
        assert ran_beside == ["other page"]
        assert [(r[0], r[2], r[3]) for r in _rows(db)] == [
            ("find-lines", "kraken:blla", "done"), ("find-lines", "kraken:blla", "done")]


def _blocked_lane(db):
    """Hold the lane with one job so the next ones queue up together, as a folder's pages do."""
    gate = threading.Event()
    started = threading.Event()

    def hold():
        started.set()
        gate.wait(10)

    first = jobs.submit(db, "find-lines", "first", model="kraken:blla", fn=hold)
    assert started.wait(10)
    return gate, first


class TestTheLaneKeepsOneModelLoaded:
    def test_a_folders_pages_run_grouped_by_reader(self, db):
        """WHY: two readers alternating page by page would swap models on every page; the lane
        finishes everything for the loaded reader first, then switches once."""
        order = []
        gate, first = _blocked_lane(db)
        futures = [jobs.submit(db, "read-a-line", name, model=f"kraken:{reader}",
                               fn=lambda name=name: order.append(name))
                   for name, reader in (("a1", "a"), ("b1", "b"), ("a2", "a"), ("b2", "b"))]
        gate.set()
        concurrent.futures.wait([first, *futures], timeout=10)
        assert order == ["a1", "a2", "b1", "b2"]

    def test_kraken_lets_go_of_its_models_before_another_heavy_model_runs(self, db, monkeypatch):
        """WHY: Kraken keeps its line finder and reader resident (2-3 GB). On an 8 GB Mac the
        embedder must not load on top of them: switching from Kraken to another heavy model
        frees Kraken's first; switching between Kraken readers does not (Kraken replaces its
        reader itself)."""
        import fichero_server.llm.kraken_runtime as kraken_runtime

        released = []
        monkeypatch.setattr(kraken_runtime, "release_resident_models", lambda: released.append(True))
        jobs.submit(db, "read-a-line", "p1", model="kraken:a", fn=lambda: None).result(10)
        jobs.submit(db, "read-a-line", "p2", model="kraken:b", fn=lambda: None).result(10)
        assert released == []
        jobs.submit(db, "read-a-line", "p3", model="embedder", fn=lambda: None).result(10)
        assert released == [True]


class TestSwitchingBetweenHeavyModels:
    def test_the_embedder_lets_go_before_kraken_runs(self, db, monkeypatch):
        """WHY: the embedder (~1.5 GB) and Kraken (2-3 GB) do not both fit an 8 GB Mac. The
        switch frees the embedder first, unless an embed or a search is using it this moment."""
        import fichero_server.db.embeddings as embeddings

        released = []
        monkeypatch.setattr(embeddings, "release_idle_embedders",
                            lambda idle_seconds=None: released.append(idle_seconds) or [])
        jobs.submit(db, "read-a-line", "p1", model="embedder", fn=lambda: None).result(10)
        jobs.submit(db, "read-a-line", "p2", model="kraken:a", fn=lambda: None).result(10)
        assert released == [0]

    def test_background_work_waits_for_a_quiet_spell_before_swapping_models(self, db, monkeypatch):
        """WHY: a run's Kraken pages come in bursts, each followed by its saved page's embed.
        Swapping to the embedder in every gap would reload Kraken on the next page and the
        embedder on the next embed, page after page. A background embed waits until Kraken has
        been quiet; a page someone is waiting for switches back at once."""
        import time

        monkeypatch.setattr(jobs, "SWITCH_AFTER_QUIET_SECONDS", 0.6)
        embedded = []
        monkeypatch.setitem(jobs.KINDS, "t-embed", jobs.Kind(
            run=lambda db, s: embedded.append(time.monotonic()), model="embedder"))
        jobs.submit(db, "find-lines", "page", model="kraken:blla", fn=lambda: None).result(10)
        kraken_done = time.monotonic()
        jobs.enqueue(db, "t-embed", "page")
        deadline = time.monotonic() + 10
        while not embedded and time.monotonic() < deadline:
            time.sleep(0.02)
        assert embedded and embedded[0] - kraken_done >= 0.5

        started = time.monotonic()
        jobs.submit(db, "find-lines", "next", model="kraken:blla", fn=lambda: None).result(10)
        assert time.monotonic() - started < 0.5


class TestAPageSomeoneIsWaitingFor:
    def test_it_runs_while_background_work_is_paused_and_says_so(self, db, monkeypatch):
        """WHY: pause stops what runs by itself; a run a person pressed is what they asked for
        (spec open question 2). The row says it ran anyway, so the pause never looks broken."""
        stored = []
        monkeypatch.setitem(jobs.KINDS, "t-stored", jobs.Kind(run=lambda db, s: stored.append(s), model=None))
        jobs.set_paused(True)
        jobs.enqueue(db, "t-stored", "held")
        seen = []

        def page():
            seen.append(db.execute_fetchone("SELECT reason FROM jobs WHERE subject = 'page'")[0])

        jobs.submit(db, "find-lines", "page", model="kraken:blla", fn=page).result(10)
        assert seen == ["Running although background work is paused"]
        assert stored == []

    def test_stop_before_it_starts_cancels_the_page(self, db):
        """WHY: Stop on a run must reach its pages still waiting for the lane, not leave them to
        run after the person stopped it."""
        gate, first = _blocked_lane(db)
        ran = []
        waiting = jobs.submit(db, "find-lines", "stopped", model="kraken:blla", fn=lambda: ran.append(1))
        assert waiting.cancel()
        gate.set()
        first.result(10)
        assert jobs.submit(db, "find-lines", "after", model="kraken:blla", fn=lambda: "ok").result(10) == "ok"
        assert ran == []
        assert db.execute_fetchone("SELECT state, reason FROM jobs WHERE subject = 'stopped'") == (
            "cancelled", "Stopped before it started")

    def test_a_failure_reaches_the_caller_and_the_row(self, db):
        """WHY: the workflow step must see Kraken's error (it reports it per page) and Activity
        must show it; a failure swallowed by the lane would leave the step waiting or blank."""
        def boom():
            raise RuntimeError("Kraken is not installed")

        with pytest.raises(RuntimeError, match="not installed"):
            jobs.submit(db, "find-lines", "page", model="kraken:blla", fn=boom).result(10)
        assert db.execute_fetchone("SELECT state, reason FROM jobs WHERE subject = 'page'") == (
            "failed", "Kraken is not installed")

    def test_after_a_restart_an_unfinished_page_is_cancelled_not_rerun(self, test_package, monkeypatch):
        """WHY: the row holds no recipe for the page (the image may be a temporary render), so
        it cannot be re-run; it is closed with a reason instead of sitting `running` forever.
        Its workflow run resumes or fails on its own terms."""
        db = db_manager.get_database(test_package)
        gate, first = _blocked_lane(db)
        db_manager.close_database(test_package)  # quit while the page runs
        gate.set()
        first.result(10)
        monkeypatch.setattr(jobs, "_scheduler", jobs._Scheduler())
        db = db_manager.get_database(test_package)
        assert db.execute_fetchone("SELECT state, reason FROM jobs WHERE subject = 'first'") == (
            "cancelled", "Its workflow run stopped before this page was done")


def test_economy_htr_reads_its_kraken_page_on_the_lane(test_package, tmp_path, monkeypatch):
    """WHY: economy HTR is the second road into Kraken; left off the lane it would load a reader
    beside whatever the lane holds."""
    import fichero_server.llm.kraken_runtime as kraken_runtime
    from fichero_server.workflows.tools.economy_htr import kraken_transcribe_page

    library = str(test_package)
    db = db_manager.get_database(library)
    threads = []

    def fake_recognize_lines(image_path, model_path):
        threads.append(threading.current_thread().name)
        return {"lines": [{"text": "vecino"}]}

    monkeypatch.setattr(kraken_runtime, "recognize_lines", fake_recognize_lines)
    monkeypatch.setattr(kraken_runtime, "resolve_recognition_model",
                        lambda ref: ("/models/mccatmus.mlmodel", "kraken-mccatmus"))
    png = _png(tmp_path / "p.png")
    assert kraken_transcribe_page(str(png), "kraken-mccatmus", library_path=library) == "vecino"
    assert threads == ["fichero-jobs"]
    assert _rows(db) == [("read-a-line", "p.png", "kraken:kraken-mccatmus", "done", None)]
