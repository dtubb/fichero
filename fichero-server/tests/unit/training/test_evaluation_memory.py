"""A bake-off's memory (#5529, #5524): its readers stay bounded, and a stop for memory keeps what it measured.

The evaluation job (`training/evaluation.py`) as the scheduler runs it, with Kraken faked at its seam
(`kraken_runtime.read_given_lines`). The fake loads its reader through Kraken's real resident-model cache
(`kraken_runtime._resident`), as the real reading does, and that reader holds a known buffer.
"""
from __future__ import annotations

import gc
import json
import tracemalloc
import weakref

import pytest

from fichero_server.execution import jobs
from fichero_server.llm import kraken_runtime
from fichero_server.llm.kraken_runtime import KrakenMemoryUnavailableError
from fichero_server.training import evaluation
from tests.unit.training.test_evaluation_job import (  # noqa: F401  (fixtures)
    BASE,
    CHECKED,
    _base_installed,
    _trained,
    homes,
    project,
)


class StubReader:
    BYTES = 8 * 1024 * 1024
    alive: "weakref.WeakSet[StubReader]" = weakref.WeakSet()

    def __init__(self, path: str):
        self.weights = bytearray(self.BYTES)
        StubReader.alive.add(self)


class Readers:
    """Reads every line as checked, loading its reader through Kraken's resident cache. `refuse` names a
    (reader, photo) whose first read the memory guard refuses."""

    def __init__(self):
        self.read: list[tuple[str, str]] = []
        self.refuse: tuple[str, str] | None = None
        self.most_alive = 0

    def __call__(self, image_path, model_path, lines, **kw):
        if self.refuse == (str(model_path), str(image_path)):
            self.refuse = None
            raise KrakenMemoryUnavailableError("Waiting: memory is tight: needs about 2.5 GB, 2.2 GB free")
        kraken_runtime._resident("read", str(model_path), lambda: StubReader(str(model_path)))
        self.most_alive = max(self.most_alive, len(StubReader.alive))
        self.read.append((str(model_path), str(image_path)))
        return [ln["text"] for ln in lines]


@pytest.fixture
def readers(monkeypatch):
    kraken_runtime.release_resident_models()
    fake = Readers()
    monkeypatch.setattr(kraken_runtime, "read_given_lines", fake)
    yield fake
    kraken_runtime.release_resident_models()


def _start(client, db, trained):
    r = client.post("/api/evaluation/runs", json={"checked": CHECKED, "candidates": [{"model": trained}]})
    assert r.status_code == 200, r.text
    job_id = r.json()["job_id"]
    kind, subject = db.execute_fetchone("SELECT kind, subject FROM jobs WHERE id = ?", [job_id])
    evaluation.register_job_kinds()
    return job_id, jobs.KINDS[kind], subject


def test_a_bake_off_stopped_for_memory_waits_and_carries_on_without_reading_a_page_twice(
        client, db, tmp_path, project, readers):  # noqa: F811 (pytest fixture)
    """#5524: "a run stopped on memory pauses and keeps what it measured".
    WHY: a Syriac bake-off read 6 of 12 pages, the memory guard stopped it, and it was marked failed with no
    partial scores. Now the job goes back to waiting with the memory reason (`JobDeferred`), and run again it
    carries on from the pages already scored: every page is read once per reader, and the scores are whole."""
    base = _base_installed(tmp_path)
    trained = _trained(client, tmp_path, project, held_out=[d.id for d in project["held"]])
    trained_path = kraken_runtime.recognition_model_path(trained)
    photos = sorted(d.path for d in project["held"])
    readers.refuse = (base, photos[1])  # the second reader, its second page
    job_id, kind, subject = _start(client, db, trained)

    with pytest.raises(jobs.JobDeferred, match="memory is tight"):
        jobs._scheduler._work(db, job_id, kind, subject, None)
    kept = json.loads(jobs.read_job(db, job_id)["detail"])["measured_so_far"]
    assert len(kept[f"{trained}|kraken"]["per_page"]) == 2 and len(kept[f"{BASE}|kraken"]["per_page"]) == 1

    result = jobs._scheduler._work(db, job_id, kind, subject, None)
    assert sorted(readers.read) == sorted((m, p) for m in (trained_path, base) for p in photos)
    by_model = {m["model"]: m for m in result["models"]}
    assert all(len(m["per_page"]) == 2 for m in by_model.values())
    assert result["best"] == trained


def test_repeated_bake_offs_keep_one_reader_in_memory(client, db, tmp_path, project, readers):  # noqa: F811 (pytest fixture)
    """#5529: the dev engine grew to 18 GB over one bake-off.
    WHY: however many bake-offs, pages and candidates, the engine holds one reader at a time (a different
    one replaces it) and the memory a bake-off leaves behind does not grow from one to the next."""
    _base_installed(tmp_path)
    trained = _trained(client, tmp_path, project, held_out=[d.id for d in project["held"]])
    tracemalloc.start()
    try:
        after = []
        for _ in range(4):
            job_id, kind, subject = _start(client, db, trained)
            jobs._scheduler._work(db, job_id, kind, subject, None)
            gc.collect()
            after.append(tracemalloc.get_traced_memory()[0])
    finally:
        tracemalloc.stop()
    assert readers.most_alive == 1
    assert after[-1] - after[0] < StubReader.BYTES // 2, after
