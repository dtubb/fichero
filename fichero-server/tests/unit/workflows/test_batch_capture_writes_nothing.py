"""A step's capture run for a provider batch writes nothing (spec: recipe-steps-at-scale, #5940).

`compute.recipe.cloud-batch-above-threshold`, design A (2026-10-28): the batch's requests are the step's own vision
calls, captured by running the step under `provider_batch.capturing()`. That run must leave the library as it found
it, no pass, no reading, no artifact, no failed page, no page text, or the replay would find the page done (or
broken) before its answer came back. The replay under `answering()` then lands the page through the same path.
"""
from __future__ import annotations

import asyncio

import pytest
from PIL import Image

import fichero_server.llm as llm
from fichero_server.llm import LLMConfig, provider_batch
from fichero_server.workflows.tools.vision_base import VisionToolConfig, process_vision

ROWS = ("documents", "artifacts", "contentrepresentations", "contentrepresentationrevisions", "segment_passes", "segments",
        "segmentversions", "renditions", "mutationlogs", "actionaudits", "workflowrunrecords", "jobs")


@pytest.fixture(autouse=True)
def _close_the_library(tmp_path):
    yield
    from fichero_server.db import db_manager

    db_manager.close_database(tmp_path)


def _library(tmp_path):
    from fichero_server.db import db_manager
    from fichero_server.models import DocType, Document, FileType

    image = tmp_path / "page.png"
    Image.new("RGB", (64, 48), "white").save(image)
    db = db_manager.get_database(tmp_path)
    doc = Document(name="page.png", doc_type=DocType.file, file_type=FileType.image, path=str(image))
    db.save(doc)
    return db, doc, image


def _state(db, doc_id):
    from fichero_server.models import Document

    counts = {t: db.execute_fetchone(f"SELECT count(*) FROM {t}")[0] for t in ROWS}  # noqa: S608 -- fixed names
    doc = db.get(Document, doc_id)
    return counts, doc.page_content, dict(doc.metadata or {})


def _read(tmp_path, image, doc, *, save_to_db=True):
    return asyncio.run(process_vision(
        files=[str(image)], documents=[{"id": doc.id, "name": doc.name}],
        prompt="Transcribe the page. Output ONLY the transcription.",
        llm_config=LLMConfig(provider="anthropic", model="claude-opus-5-5"), library_path=str(tmp_path), task_id=None,
        tool_config=VisionToolConfig(artifact_type="transcription"), save_to_db=save_to_db))


def test_the_capture_run_writes_nothing_and_the_replay_lands_the_answer(tmp_path, monkeypatch):
    monkeypatch.setattr(llm, "_enforce_local_only_provider", lambda config, kind: None)
    monkeypatch.setattr(llm, "get_langchain_model", lambda config: (_ for _ in ()).throw(AssertionError("a plain call")))
    db, doc, image = _library(tmp_path)
    before = _state(db, doc.id)

    with provider_batch.capturing(answer=lambda prompt: "En la villa de Madrid") as captured:
        _read(tmp_path, image, doc)

    assert len(captured) == 1, "the page's one call is captured"
    assert _state(db, doc.id) == before, "the capture run left the library as it found it"

    with provider_batch.answering({captured[0].key: "En la villa de Madrid"}):
        result = _read(tmp_path, image, doc)
    assert result["texts"] == ["En la villa de Madrid"]
    assert _state(db, doc.id) != before, "the replay landed the answer through the normal path"
