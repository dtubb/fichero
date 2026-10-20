"""A stage's try compares 2 or 3 of its step's candidates side by side (#5668, Daniel: onboarding teaches by
comparison), tested to the spec: `source.onboard.stages.compares-candidates`
(docs/contributor_manual/specs/source/models-chains-and-projects.md, section 7d).

Each candidate runs on its own copy of the sample pages; its column is the bake-off row's fields with its own
result and how it was compared. The models are faked at the runner's one seam (`_run_workflow`), the region
finders at theirs; the copying, the plan and the measures are the engine's own.
"""

from __future__ import annotations

import threading

from pathlib import Path

import pytest
from PIL import Image

from fichero_server.execution import jobs
from fichero_server.models import ContentRepresentation, DocType, Document, FileType
from fichero_server.models.anchors import SourceAnchor
from fichero_server.models.knowledge import KnowledgeEntity
from fichero_server.recipes import runner, samples
from tests.unit.recipes.test_models_ux_5619 import ollama  # noqa: F401  (fixture: the person's Ollama, this Mac)

SPACY = "spacy:pkg/es_core_news_sm@bundled"


def _pages(db, tmp_path, n: int = 2) -> list[Document]:
    out = []
    for i in range(n):
        path = tmp_path / "scans" / f"{i + 1}_Hoja_{530 + i}_Recto.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (200, 300), (235, 230, 220)).save(path)
        doc = Document(name=path.name, doc_type=DocType.file, file_type=FileType.image, path=str(path),
                       page_content="Muy señor mío")  # a page with text: Names needs Read (#5687)
        db.save(doc)
        out.append(doc)
    return out


def _set_up(client, jobs_asked):
    answers = {"purposes": ["transcribe"], "languages": ["es"], "scripts": ["Latn"], "materials": ["handwriting"],
               "jobs": jobs_asked, "cloud_allowed": False}
    recipe = client.post("/api/recipes/assemble", json=answers).json()
    assert client.put("/api/recipes/project", json={"answers": answers, "recipe": recipe}).status_code == 200
    return recipe


def _run(db, started):
    job = jobs.read_job(db, started["job_id"])
    samples.register_job_kinds()
    jobs.KINDS[samples.TRY_KIND].run(db, job["subject"])


def test_names_is_compared_by_its_step_and_the_finders_next_candidate(client, db, tmp_path, monkeypatch, ollama,
                                                                      jobs_run_by_the_test):
    """"without them the stage's main step … is compared with its own model first and the per-step finder's next
    one or two runnable on this Mac … for Names … the count of what it found and the items no other candidate
    found." Each candidate on its own copy; the project untouched; the try's own fields are the step's own."""
    pages = _pages(db, tmp_path)
    _set_up(client, ["find-names-tag-words"])
    found_by = {"es_core_news_sm": ["Juan de la Cruz", "Popayán"], "llama3.2:latest": ["Juan de la Cruz", "Cartagena"]}
    ran_in = []

    def fake_run(copy, card, documents, parent):
        ran_in.append((Path(copy.path).parent.name, card["model_override"]))
        for name in found_by[card["model_override"]]:
            copy.save(KnowledgeEntity(canonical_name=name, entity_type="person", source_document_ids=[documents[0]]))
        return "thread-x", "done", None

    monkeypatch.setattr(runner, "_run_workflow", fake_run)
    before = len(db.all(KnowledgeEntity))
    started = client.post("/api/recipes/stages/names/try", json={})
    assert started.status_code == 200, started.text
    columns = started.json()["candidates"]
    assert [c["card"] for c in columns][0] == SPACY and len(columns) == 2, columns
    _run(db, started.json())

    result = client.get("/api/recipes/stages/names/try").json()
    assert result["state"] == "done", result
    spacy, llama = result["candidates"]
    assert spacy["card"] == SPACY and llama["pin"]["model"] == "llama3.2:latest"
    assert {n["name"] for n in spacy["names"]} == {"Juan de la Cruz", "Popayán"}
    assert spacy["measures"]["kind"] == "items" and spacy["measures"]["found"] == 2
    assert spacy["measures"]["only_this_found"] == ["Popayán"] and llama["measures"]["only_this_found"] == ["Cartagena"]
    assert spacy["agreement"] == pytest.approx(1 / 3, abs=0.01)
    for column in (spacy, llama):
        assert column["runs_on"] == "this-mac" and column["local"] is True
        assert column["cost_usd"]["value"] == 0.0 and column["seconds"] is not None and column["why"] is None
    assert {n["name"] for n in result["names"]} == {"Juan de la Cruz", "Popayán"}  # the step's own, as before
    assert len({folder for folder, _ in ran_in}) == 2  # one copy each
    assert len(db.all(KnowledgeEntity)) == before  # nothing written as the project's work


def test_find_regions_is_compared_by_the_overlap_of_its_shapes(client, db, tmp_path, monkeypatch,
                                                              jobs_run_by_the_test):
    """"for Find Regions and Find Lines the overlap of its shapes with the others' (mean best IoU)". Named
    candidates: Kraken's segmenter and the YOLO layout model."""
    from fichero_server.llm import kraken_runtime, yolo_runtime

    _pages(db, tmp_path, 1)
    _set_up(client, ["find-regions"])
    monkeypatch.setattr(kraken_runtime, "segment_lines", lambda path, **k: {
        "width": 200, "height": 300, "lines": [],
        "regions": [{"id": "r1", "type": "text", "polygon": [[20, 30], [120, 30], [120, 180], [20, 180]]}]})
    monkeypatch.setattr(yolo_runtime, "detect_regions", lambda path, model_id=None, **k: [
        yolo_runtime.Region(kind_raw="Text", rect=[0.1, 0.1, 0.5, 0.4], confidence=0.9)])
    monkeypatch.setattr(yolo_runtime, "is_installed", lambda model_id: True)  # here: nothing to fetch (#5687)
    named = ["kraken:builtin/blla@bundled", "yolo:hf/hantian/yolo-doclaynet/yolov11n@unpinned"]

    started = client.post("/api/recipes/stages/find-regions/try", json={"candidates": named})
    assert started.status_code == 200, started.text
    _run(db, started.json())

    result = client.get("/api/recipes/stages/find-regions/try").json()
    kraken, yolo = result["candidates"]
    assert [kraken["card"], yolo["card"]] == named
    assert kraken["measures"]["kind"] == "shapes" and yolo["measures"]["kind"] == "shapes"
    assert kraken["agreement"] == pytest.approx(0.8, abs=0.01) == yolo["agreement"]  # 0.5×0.4 inside 0.5×0.5
    assert kraken["per_page"][0]["segments"] == {"region": 1}


def test_a_try_of_find_regions_is_served_by_the_real_lane_on_its_scratch_copy(client, db, tmp_path, monkeypatch,
                                                                              real_model_lane):
    """The try runs on a scratch copy of the pages (`samples._run_one`); Kraken's segmenter there goes through the model
    lane, and the lane must serve the copy: with the real scheduler (no `jobs_run_by_the_test`, no inline lane) the try
    finishes. Production hangs the way the harness did (M4, 14f3f1216: `wake` stubbed, nothing served the page) only if this fails."""
    from fichero_server.llm import kraken_runtime

    _pages(db, tmp_path, 1)
    _set_up(client, ["find-regions"])
    monkeypatch.setattr(kraken_runtime, "segment_lines", lambda path, **k: {
        "width": 200, "height": 300, "lines": [],
        "regions": [{"id": "r1", "type": "text", "polygon": [[20, 30], [120, 30], [120, 180], [20, 180]]}]})
    started = client.post("/api/recipes/stages/find-regions/try", json={"candidates": ["kraken:builtin/blla@bundled"]})
    assert started.status_code == 200, started.text
    done = threading.Event()
    threading.Thread(target=lambda: (_run(db, started.json()), done.set()), daemon=True).start()
    assert done.wait(30), "the try's page waited for a lane that never served the scratch copy"
    result = client.get("/api/recipes/stages/find-regions/try").json()
    assert result["state"] == "done" and result["candidates"][0]["per_page"][0]["segments"] == {"region": 1}, result


def test_read_is_compared_by_agreement_and_by_errors_on_lines_a_person_corrected(client, db, tmp_path, monkeypatch,
                                                                                jobs_run_by_the_test):
    """"for Read … the text's agreement with the other candidates (1 less their character distance) and its
    character error rate on lines a person corrected on these pages"."""
    from fichero_server.training import evaluation

    (page,) = _pages(db, tmp_path, 1)
    _set_up(client, ["find-lines", "read-a-line"])
    def fake_run(copy, card, documents, parent):
        """The candidate Kraken reader reads (the first one as the person did, the other with two letters wrong);
        the stage's other steps (Correct) make nothing here."""
        model = str(card["model_override"])
        text = "Muy señor mío" if "21788410" in model else "May señar mío"
        for doc_id in documents if card.get("provider_override") == "kraken" or model.startswith("kraken") else ():
            copy.save(ContentRepresentation(document_id=doc_id, kind="transcription", content=text,
                                            source_anchor=SourceAnchor(document_id=doc_id)))
        return "thread-x", "done", None

    monkeypatch.setattr(runner, "_run_workflow", fake_run)
    # The two readers are on this Mac: nothing to fetch before they run (#5687 fetches what is not).
    monkeypatch.setattr("fichero_server.recipes.start.missing_models", lambda runs: [])
    monkeypatch.setattr("fichero_server.recipes.start.runtime_to_set_up", lambda runs: [])
    monkeypatch.setattr("fichero_server.recipes.start.local_models_to_download", lambda runs: [])
    monkeypatch.setattr(evaluation, "reference_page", lambda db, page_id, checked: (
        {"lines": [{"id": "l1", "text": "Muy señor mío"}]}, None) if page_id == page.id else (None, "not checked"))
    named = ["kraken:zenodo/10.5281/zenodo.21788410@unpinned", "kraken:zenodo/10.5281/zenodo.13788177@unpinned"]

    started = client.post("/api/recipes/stages/read/try", json={"candidates": named})
    assert started.status_code == 200, started.text
    _run(db, started.json())

    first, second = client.get("/api/recipes/stages/read/try").json()["candidates"]
    assert first["measures"]["kind"] == "text"
    assert first["cer"] == 0.0 and second["cer"] == pytest.approx(2 / 13, abs=0.01), (first["measures"], first["why"])
    assert first["agreement"] == second["agreement"] and 0.8 < first["agreement"] < 1.0


def test_a_cloud_candidate_says_its_cost_and_runs_only_with_the_yes(client, db, tmp_path, monkeypatch):
    _pages(db, tmp_path)
    _set_up(client, ["find-names-tag-words"])
    monkeypatch.setattr(samples, "_stage_plan", lambda db, stage, setup, n: {
        "refusals": [], "estimate": {"total_cost_usd": 0.05},
        "runs": [{"steps": ["find-names-tag-words"], "card": "workflow", "runs_on": "cloud:openai",
                  "model_override": "gpt-x", "workflow": "W"}],
        "workflows": [{"steps": ["find-names-tag-words"], "model_override": "gpt-x", "runs_on": "cloud:openai",
                       "workflow": "W"}]})
    refused = client.post("/api/recipes/stages/names/try", json={})
    assert refused.status_code == 402 and "$0.05" in refused.json()["detail"], refused.text
    assert client.post("/api/recipes/stages/names/try", json={"cost_ok": True}).status_code == 200
