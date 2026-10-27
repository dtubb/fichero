"""The onboarding journey with a recipe that reads, driven through the generated MCP tools (#5704), tested to the
spec: `openapi.mcp.onboarding-journey` (docs/contributor_manual/specs/harness/surfaces-from-openapi.md).

The model is stubbed where the recipe tests stub it, at the model boundary only (`test_recipe_execution_to_spec.
Cards`: a Kraken reader at the Kraken runtime; spaCy's entity finder at `spacy_ner.extract_entities`); the real job
scheduler runs Start → find the lines and read them → find names → the summary. One of the three pages is read
unsurely, so Names leaves it out and the run says why (#5694).
"""

from __future__ import annotations

import time

import pytest

from fichero_server.execution import jobs
from fichero_server.models import DocType, Document, FileType
from tests.unit.mcp.test_onboarding_journey_through_mcp import CEILING, _call, agent  # noqa: F401  (fixture)
from tests.unit.recipes.test_recipe_execution_to_spec import Cards, _png

SPACY = {"spacy": "es_core_news_sm", "version": "3.8.0"}
RECIPE = {"fichero_recipe": 1, "id": "t/reading-journey", "version": "0.1.0", "title": "Reading journey", "steps": [
    {"id": "lines", "job": "find-lines", "model": {"kraken": "blla", "kraken_version": "bundled"}},
    {"id": "read", "job": "read-a-line", "model": {"zenodo": "10.5281/zenodo.13788177"}},
    {"id": "names", "job": "find-names-tag-words", "model": SPACY},
]}
UNSURE = "p2.png"


class UnsureCards(Cards):
    """The recipe tests' Kraken reader, sure of two pages and unsure of the third."""

    def recognize(self, image_path, model_path, **kw):
        result = super().recognize(image_path, model_path, **kw)
        sure = 0.42 if str(image_path).endswith(UNSURE) else 0.95
        for box in result.boxes:
            box.confidence = sure
        return result


@pytest.fixture
def engine(monkeypatch, app_db):
    """The recipe tests' engine: a fresh scheduler, the pause off, the readers stubbed at the model boundary."""
    from fichero_server.importers import derivatives
    from fichero_server.knowledge import spacy_ner
    from fichero_server.llm import kraken_runtime, local_models
    from fichero_server.workflows import validation

    monkeypatch.setattr(jobs, "_scheduler", jobs._Scheduler())
    jobs.set_paused(False)
    derivatives.register_job_kinds()
    for kind in (derivatives.THUMBNAIL_KIND, derivatives.EMBED_KIND, derivatives.NLP_KIND):
        monkeypatch.setitem(jobs.KINDS, kind, jobs.Kind(run=lambda db, subject: None, model=None))
    cards = UnsureCards()
    monkeypatch.setattr(kraken_runtime, "recognize_to_geometry", cards.recognize)
    # Find Lines calls the segmenter here; unstubbed, real Kraken segmented every page (#6222). No lines on these
    # small pages, so Read reads the page (`recognize` above), as the recipe tests' engine does.
    monkeypatch.setattr(kraken_runtime, "segment_lines",
                        lambda image_path, **kw: {"width": 32, "height": 32, "regions": [], "lines": []})
    monkeypatch.setattr(kraken_runtime, "resolve_recognition_model",
                        lambda ref: ("/models/mccatmus.mlmodel", "kraken-mccatmus"))
    # The reader is on this Mac, whatever this machine holds: Start never queues its download (no network).
    monkeypatch.setattr(kraken_runtime, "recognition_model_path", lambda name: "/models/mccatmus.mlmodel")
    monkeypatch.setattr(local_models, "spacy_pipeline_available", lambda name: True)
    monkeypatch.setattr(validation, "validate_workflow_llm_preflight", lambda *a, **k: [])
    named: list[str] = []

    def extract(text, language=None, model=None, **kw):
        named.append(text)
        return []

    monkeypatch.setattr(spacy_ner, "extract_entities", extract)
    cards.named = named
    yield cards
    jobs.set_paused(False)
    jobs.stop(None)  # this test's scheduler threads end with it, never at interpreter exit


def assert_no_download(db) -> None:
    """A unit test never fetches a model: no download job was queued."""
    from fichero_server.llm.local_models import DOWNLOAD_KIND

    queued = db.execute_fetchall("SELECT id, reason FROM jobs WHERE kind = ?", [DOWNLOAD_KIND])
    assert not queued, f"a model download was queued: {queued}"


def test_the_reading_journey_through_mcp(agent, client, db, tmp_path, test_package, engine):  # noqa: F811
    from fichero_server.workflows.default_workflows import seed_default_workflows

    seed_default_workflows(db)
    folder = Document(name="Box", doc_type=DocType.folder)
    db.save(folder)
    for i in range(3):
        db.save(Document(name=f"p{i}.png", doc_type=DocType.file, file_type=FileType.image, parent_id=folder.id,
                         path=str(_png(tmp_path / f"p{i}.png"))))

    _call(agent, "fichero_use_library", {"path": str(test_package)})
    _call(agent, "fichero_recipes_save_project_setup",
          {"answers": {"purposes": ["transcribe"], "languages": ["es"], "scripts": ["Latn"]}, "recipe": RECIPE})
    plan = _call(agent, "fichero_recipes_get_start_plan", {})
    assert not plan["refusals"], plan["refusals"]
    run_id = _call(agent, "fichero_recipes_start_project", {})["started"]["job_id"]

    deadline, status = time.monotonic() + 120, {}
    while time.monotonic() < deadline:
        status = _call(agent, "fichero_recipes_run_status", {"job_id": run_id})
        if status["state"] in ("done", "failed", "cancelled"):
            break
        time.sleep(0.5)
    assert status.get("state") == "done", status
    assert sorted(engine.read) == ["p0.png", "p1.png", "p2.png"], "the three pages were read"
    assert engine.named, "the names step read the pages"

    names = next(s for s in status["steps"] if "names" in s["steps"])
    (left,) = names["left_out"]
    assert left["page"] == UNSURE and "too uncertain to find names" in left["why"], left
    summary = _call(agent, "fichero_recipes_run_summary", {"job_id": run_id})
    assert any(line.startswith("Left out: ") and UNSURE in line for line in summary["lines"]), summary["lines"]
    assert "Names not looked for on 1 page: their reading is too uncertain" in summary["lines"], summary["lines"]
    assert_no_download(db)
