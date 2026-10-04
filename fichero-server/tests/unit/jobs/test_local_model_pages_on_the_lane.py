"""A page read by a model served on this Mac (MLX, Ollama, LM Studio) holds the local-model lane.

Spec: docs/contributor_manual/specs/ui/activity-and-automatic-work.md -- `activity.lane.*`,
`activity.kraken-mlx-inference-visible`; ai/local-runtimes.md section 3 ("the Mac holds one heavy
model at a time unless two fit"). Before this, an MLX page and a Kraken page (or the embedder) ran
at the same time, two heavy models in one Mac's memory. The model call itself is faked here.
"""
from __future__ import annotations

import asyncio
import threading

import pytest

from fichero_server.db.manager import db_manager
from fichero_server.execution import jobs


def _page(db, tmp_path):
    from PIL import Image

    from fichero_server.models import DocType, Document, FileType

    path = tmp_path / "hand.png"
    Image.new("RGB", (16, 16), (255, 255, 255)).save(str(path), format="PNG")
    doc = Document(name="hand.png", doc_type=DocType.file, file_type=FileType.image, path=str(path))
    db.save(doc)
    return doc


async def _transcribe(library_path, doc, provider, task_id=None):
    from fichero_server.llm import LLMConfig
    from fichero_server.workflows.tools.sources import files_tool
    from fichero_server.workflows.tools.transcribe import transcribe

    config = LLMConfig(provider=provider, model="mlx-community/reader")
    src = await files_tool(inputs={}, state={"selected_doc_ids": [doc.id], "library_path": library_path},
                           llm_config=config)
    return await transcribe(inputs={"files": src["files"], "documents": src["documents"], "regions_first": False},
                            state={"library_path": library_path, "task_id": task_id}, llm_config=config)


def _rows(db):
    return db.execute_fetchall("SELECT kind, subject, model, state FROM jobs WHERE kind = 'read-a-page'")


@pytest.mark.asyncio
async def test_an_mlx_page_holds_the_lane_while_it_reads(test_package, tmp_path, monkeypatch):
    """WHY: Kraken (2-3 GB) loading while an MLX reader is answering puts two heavy models in
    memory at once. While the page reads, a Kraken page handed to the lane must wait; the read
    waits up to a second for that Kraken page, which only runs early if the lane is NOT held."""
    import fichero_server.llm as llm

    library = str(test_package)
    db = db_manager.get_database(library)
    doc = _page(db, tmp_path)
    order = []
    kraken_ran = threading.Event()

    async def fake_vision(images, prompt, config, **kwargs):
        kraken = jobs.submit(db, "find-lines", "other", model="kraken:blla",
                             fn=lambda: (order.append("kraken"), kraken_ran.set()))
        await asyncio.to_thread(kraken_ran.wait, 1.0)
        order.append("read")
        fake_vision.kraken = kraken
        return "vecino de la ciudad"

    monkeypatch.setattr(llm, "vision", fake_vision)
    result = await _transcribe(library, doc, "omlx")
    assert not result.get("error"), result.get("error")
    fake_vision.kraken.result(30)
    assert order == ["read", "kraken"]
    assert _rows(db) == [("read-a-page", doc.id, "omlx:mlx-community/reader", "done")]


@pytest.mark.asyncio
async def test_activity_run_lane_cap_per_mac__a_cloud_page_takes_the_network_lane_not_the_model_lane(
        test_package, tmp_path, monkeypatch):
    """Behaviour `activity.run.lane-cap-per-mac` (cloud calls share one cap per Mac, on the network
    lane) with `activity.throttle.lanes` ("jobs run in lanes by resource"): a cloud call waits on the
    network, not on this Mac's memory, so while a heavy model holds the local-model lane the cloud
    page still runs, and its row is on the network lane, named by its model."""
    import fichero_server.llm as llm

    library = str(test_package)
    db = db_manager.get_database(library)
    doc = _page(db, tmp_path)
    gate, started = threading.Event(), threading.Event()
    heavy = jobs.submit(db, "find-lines", "heavy", model="kraken:blla", fn=lambda: (started.set(), gate.wait(30)))
    assert await asyncio.to_thread(started.wait, 30)

    async def fake_vision(images, prompt, config, **kwargs):
        return "vecino de la ciudad"

    monkeypatch.setattr(llm, "vision", fake_vision)
    try:
        result = await asyncio.wait_for(_transcribe(library, doc, "openai"), 30)
    finally:
        gate.set()
    heavy.result(30)
    assert not result.get("error"), result.get("error")
    assert _rows(db) == [("read-a-page", doc.id, "openai:mlx-community/reader", "done")]


@pytest.mark.asyncio
async def test_stop_withdraws_a_held_page_still_waiting(db, test_package):
    """WHY: Stop must reach a local-model page queued behind other heavy work, as it does a
    Kraken page; it must not read after the person stopped the run."""
    from fichero_server.execution.cancellation import WorkflowCancelled, clear_cancellation, request_cancellation

    gate, started = threading.Event(), threading.Event()
    first = jobs.submit(db, "find-lines", "first", model="kraken:blla",
                        fn=lambda: (started.set(), gate.wait(10)))
    assert await asyncio.to_thread(started.wait, 10)
    read = []

    async def work():
        read.append(1)

    waiting = asyncio.ensure_future(jobs.hold_lane(str(test_package), "read-a-page", "page",
                                                   model="omlx:reader", work=work, run_id="run-mlx"))
    try:
        await asyncio.sleep(0.3)
        request_cancellation("run-mlx")
        with pytest.raises(WorkflowCancelled):
            await asyncio.wait_for(waiting, 10)
    finally:
        gate.set()
        clear_cancellation("run-mlx")
    first.result(10)
    assert read == []
    assert db.execute_fetchone("SELECT state FROM jobs WHERE subject = 'page'") == ("cancelled",)


def test_local_model_servers_are_one_family_for_the_quiet_spell():
    """WHY: switching between two MLX readers is not a heavy-model swap the lane should wait
    out; switching from MLX to Kraken is."""
    assert jobs._family("omlx:a") == jobs._family("ollama:b") == "local-model"
    assert not jobs._heavy_switch("omlx:a", "omlx:b")
    assert jobs._heavy_switch("omlx:a", "kraken:blla")
