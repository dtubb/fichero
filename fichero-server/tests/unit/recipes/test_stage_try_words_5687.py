"""A stage's try fetches what it needs and says everything in words (#5687), tested to the spec:
`source.onboard.stages.compares-candidates` and `source.onboard.models.licence-accepted-once`
(docs/contributor_manual/specs/source/models-chains-and-projects.md).

WHY: the overnight MCP walk (2026-10-11): a Find Regions try with YOLO failed "FileNotFoundError: The layout model
yolo-doclaynet-11n is not downloaded" though its card says it downloads when first used; every candidate's why
began with an exception's class name; AGPL-3.0 was called "not open"; a Find Regions try's measures said nothing of
what it found; a Names try on pages with no reading said "done, found 0".
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from PIL import Image

from fichero_server.execution import jobs
from fichero_server.models import DocType, Document, FileType
from fichero_server.recipes import samples

YOLO = "yolo:hf/hantian/yolo-doclaynet/yolov11n@unpinned"
KRAKEN = "kraken:builtin/blla@bundled"


def _pages(db, tmp_path, n: int = 1) -> list[Document]:
    out = []
    for i in range(n):
        path = tmp_path / f"{i + 1}_page.png"
        Image.new("RGB", (200, 300), (235, 230, 220)).save(path)
        doc = Document(name=path.name, doc_type=DocType.file, file_type=FileType.image, path=str(path))
        db.save(doc)
        out.append(doc)
    return out


def _set_up(client, jobs_asked):
    answers = {"purposes": ["transcribe"], "languages": ["es"], "scripts": ["Latn"], "materials": ["handwriting"],
               "jobs": jobs_asked, "cloud_allowed": False}
    recipe = client.post("/api/recipes/assemble", json=answers).json()
    assert client.put("/api/recipes/project", json={"answers": answers, "recipe": recipe}).status_code == 200


def _run(db, started):
    job = jobs.read_job(db, started["job_id"])
    samples.register_job_kinds()
    jobs.KINDS[samples.TRY_KIND].run(db, job["subject"])


def test_a_copyleft_licence_is_said_as_copyleft_not_closed():
    from fichero_server.recipes.assemble import _licence_words

    assert _licence_words("AGPL-3.0") == "its licence, AGPL-3.0, is copyleft: accept it to use it"
    assert _licence_words("Qwen-Research") == "its licence, Qwen-Research, needs accepting: accept it to use it"
    assert "not open" not in _licence_words("")


def test_a_candidate_whose_model_is_not_here_is_fetched_first_and_its_why_is_a_sentence(
        client, db, tmp_path, monkeypatch, jobs_run_by_the_test):
    """"a candidate whose model is not on this Mac is fetched before it runs … one that cannot be fetched says why,
    in words. Every why is a sentence, never an exception's class name.\""""
    from fichero_server.llm import kraken_runtime, local_models, yolo_runtime

    _pages(db, tmp_path)
    _set_up(client, ["find-regions"])
    fetched = []
    monkeypatch.setattr(yolo_runtime, "is_installed", lambda model_id: bool(fetched))
    monkeypatch.setattr(local_models, "enqueue_download",
                        lambda db, runtime, model, started_by=None: fetched.append(model) or "download-1")
    monkeypatch.setattr(jobs, "read_job", lambda db, job_id, _real=jobs.read_job: (
        {"id": job_id, "state": "done", "reason": None} if job_id == "download-1" else _real(db, job_id)))
    monkeypatch.setattr(yolo_runtime, "detect_regions", lambda path, model_id=None, **k: [
        yolo_runtime.Region(kind_raw="Text", rect=[0.1, 0.1, 0.5, 0.4], confidence=0.9)])

    def broken(path, **k):
        raise kraken_runtime.KrakenSegmentationError("Kraken segmentation failed: the page is blank")

    monkeypatch.setattr(kraken_runtime, "segment_lines", broken)

    started = client.post("/api/recipes/stages/find-regions/try", json={"candidates": [YOLO, KRAKEN]})
    assert started.status_code == 200, started.text
    _run(db, started.json())

    yolo, kraken = client.get("/api/recipes/stages/find-regions/try").json()["candidates"]
    assert fetched == ["yolo-doclaynet-11n"]  # fetched as Start fetches it, then it ran
    assert yolo["why"] is None and yolo["measures"]["found"] == 1 and yolo["measures"]["kinds"] == {"Text": 1}
    assert kraken["why"] and not kraken["why"].split(":")[0].endswith("Error"), kraken["why"]


def test_a_stage_that_needs_read_is_refused_in_words_on_pages_with_no_reading(client, db, tmp_path):
    """"A stage that needs Read …, tried on pages that have no reading yet, is refused (422): 'These pages have no
    reading yet: Names needs Read.'\""""
    _pages(db, tmp_path, 2)
    _set_up(client, ["find-names-tag-words"])
    refused = client.post("/api/recipes/stages/names/try", json={})
    assert refused.status_code == 422
    assert refused.json()["detail"].startswith("These pages have no reading yet: Names needs Read.")
