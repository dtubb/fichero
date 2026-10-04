"""spaCy pipelines download as files, are loaded by path, are pinned honestly, and a missing one is offered at
Start (#5367), tested to the spec: `runtime.spacy.pipelines-download-as-data`, `runtime.spacy.store-first`,
`runtime.spacy.pin-is-honoured` (docs/contributor_manual/specs/ai/local-runtimes.md) and
`source.recipe.missing-model-offered` (docs/contributor_manual/specs/source/models-chains-and-projects.md).

Through the public routes (`/api/local-models`, the workflow execute route, the recipe Start plan) and the real job
scheduler. No network: the "release archive" is a wheel built here from the bundled Spanish pipeline's data folder,
relabelled `es_core_news_md`, served from a `file://` URL. spaCy itself is real: a pipeline loaded from the store
reads the page.
"""
from __future__ import annotations

import json
import time
import zipfile
from pathlib import Path

import pytest

from fichero_server.execution import jobs

NAME, VERSION = "es_core_news_md", "3.8.0"
DATA = f"{NAME}/{NAME}-{VERSION}/"


def _bundled_data() -> Path:
    import es_core_news_sm

    pkg = Path(es_core_news_sm.__file__).parent
    return next(p for p in pkg.iterdir() if p.is_dir() and p.name.startswith("es_core_news_sm-"))


def _wheel(path: Path, *, extra: dict[str, bytes] | None = None, meta_name: str = "core_news_md") -> Path:
    """A release archive shaped like spaCy's: the package's code beside its data folder."""
    src = _bundled_data()
    with zipfile.ZipFile(path, "w") as z:
        z.writestr(f"{NAME}/__init__.py", "raise SystemExit('package code must never run')\n")
        z.writestr(f"{NAME}-{VERSION}.dist-info/METADATA", "Name: es-core-news-md\n")
        for f in src.rglob("*"):  # noqa: rglob is the fixture's own copy of a model folder
            if f.is_file():
                rel = f.relative_to(src).as_posix()
                data = f.read_bytes()
                if rel == "meta.json":
                    meta = json.loads(data)
                    meta["name"] = meta_name
                    data = json.dumps(meta).encode()
                z.writestr(DATA + rel, data)
        for name, data in (extra or {}).items():
            z.writestr(name, data)
    return path


@pytest.fixture
def store(monkeypatch, tmp_path, app_db):
    """An empty model store, a release archive URL pointing at a local file, a fresh scheduler."""
    from fichero_server.llm import local_models

    models = tmp_path / "models"
    monkeypatch.setattr(local_models, "MODELS_BASE", models)
    archive = {"path": _wheel(tmp_path / "release.whl")}
    monkeypatch.setattr(local_models, "SPACY_RELEASE_URL", lambda name, version: archive["path"].as_uri())
    monkeypatch.setattr(jobs, "_scheduler", jobs._Scheduler())
    jobs.set_paused(False)
    from fichero_server.knowledge import spacy_ner

    monkeypatch.setattr(spacy_ner, "_pipelines", {})
    return {"models": models, "archive": archive, "tmp": tmp_path}


def _download(client, db, name=NAME):
    r = client.post(f"/api/local-models/download/spacy/{name}")
    assert r.status_code == 200, r.text
    job_id = r.json()["job_id"]
    end = time.monotonic() + 60
    while time.monotonic() < end:
        row = jobs.read_job(db, job_id)
        if row["state"] in ("done", "failed", "cancelled"):
            return row
        time.sleep(0.1)
    raise AssertionError("download did not finish")


def _listed(client, name=NAME):
    rows = client.get("/api/local-models", params={"model_type": "spacy"}).json()["models"]
    return next(r for r in rows if r["model_id"] == name)


def test_runtime_spacy_pipelines_download_as_data__only_the_data_folder_is_written(client, db, store):
    """runtime.spacy.pipelines-download-as-data: "its release archive is fetched, only the pipeline's data folder
    (its `config.cfg`, `meta.json` and weights) is written into the model store (`<models>/spacy/<name>-<version>`),
    nothing outside that folder is written ... Installed state, size and delete then work as for Whisper ...
    The download is a `download-model` job on the network lane."""
    assert _listed(client)["is_downloaded"] is False
    row = _download(client, db)
    assert row["state"] == "done", row
    assert row["kind"] == "download-model" and jobs.KINDS["download-model"].lane == "network"
    folder = store["models"] / "spacy" / f"{NAME}-{VERSION}"
    assert (folder / "config.cfg").is_file() and (folder / "meta.json").is_file() and (folder / "ner").is_dir()
    written = [p.relative_to(store["models"]).as_posix() for p in store["models"].rglob("*")]  # noqa: rglob of a tmp store
    assert not [p for p in written if p.endswith(".py") or "dist-info" in p], "nothing outside the data folder"
    listed = _listed(client)
    assert listed["is_downloaded"] is True and listed["size_bytes"] > 1_000_000 and listed["path"] == str(folder)

    r = client.delete(f"/api/local-models/spacy/{NAME}")
    assert r.status_code == 200, r.text
    assert r.json()["freed_bytes"] == listed["size_bytes"] and not folder.exists()
    assert _listed(client)["is_downloaded"] is False


@pytest.mark.parametrize("extra", [{DATA + "code.py": b"import os\n"}, {DATA + "ner/model.so": b"\x7fELF"},
                                   {DATA + "../../escape.cfg": b"x"}, "another-pipeline"],
                         ids=["python-in-data", "compiled-in-data", "path-leaves-folder", "another-pipeline"])
def test_runtime_spacy_pipelines_download_as_data__code_in_the_data_folder_is_refused(client, db, store, extra):
    """runtime.spacy.pipelines-download-as-data: "an archive whose data folder holds code (a `.py`, compiled module
    or link) or a path that leaves the folder, or one that is not the pipeline asked for (its meta names another),
    is refused, writing nothing"."""
    if extra == "another-pipeline":
        store["archive"]["path"] = _wheel(store["tmp"] / "bad.whl", meta_name="core_news_sm")
    else:
        store["archive"]["path"] = _wheel(store["tmp"] / "bad.whl", extra=extra)
    row = _download(client, db)
    assert row["state"] == "failed", row
    assert "refused" in (row["reason"] or ""), row
    leftovers = list((store["models"] / "spacy").glob("*")) if (store["models"] / "spacy").exists() else []
    assert leftovers == [], leftovers
    assert not (store["tmp"] / "escape.cfg").exists()


def test_runtime_spacy_pipelines_download_as_data__a_bundled_pipeline_cannot_be_deleted(client, store):
    """runtime.spacy.pipelines-download-as-data: "the bundled pipelines are listed as bundled and cannot be
    deleted"."""
    assert _listed(client, "es_core_news_sm")["is_downloaded"] is True
    assert client.delete("/api/local-models/spacy/es_core_news_sm").status_code == 409


def test_runtime_spacy_pin_is_honoured_and_loaded_from_the_store(client, db, store, tmp_path):
    """runtime.spacy.store-first and runtime.spacy.pin-is-honoured: "a step pinned to a spaCy pipeline runs that
    pipeline and no other; if it is not on this Mac the step says so and does not run another in its place";
    the names step looks "for a pipeline in the model store first". The downloaded pipeline is loaded by path and
    reads the page (real spaCy)."""
    from tests.unit.kg.test_entity_says_who_made_it_to_spec import _entities, _names_run, pages  # noqa: F401

    from PIL import Image

    from fichero_server.models import DocType, Document, FileType
    from fichero_server.workflows.default_workflows import seed_default_workflows

    seed_default_workflows(db)
    Image.new("RGB", (32, 32), "white").save(tmp_path / "page.png")
    page = Document(name="page.png", doc_type=DocType.file, file_type=FileType.image, path=str(tmp_path / "page.png"),
                    page_content="Don Juan de Mosquera vendió una casa en Popayán a Isabel de Rojas.")
    db.save(page)

    from fichero_server.workflows.default_workflows import preset_workflow_id

    r = client.post("/api/workflow-execution/execute", json={
        "workflow_id": preset_workflow_id("2 · Extract Entities"), "inputs": {"selected_doc_ids": [page.id]},
        "provider_override": "spacy", "model_override": NAME})
    thread, status = r.json()["thread_id"], {}
    end = time.monotonic() + 60
    while time.monotonic() < end and status.get("status") not in ("completed", "failed"):
        time.sleep(0.1)
        got = client.get(f"/api/workflow-execution/threads/{thread}/status")
        status = got.json() if got.status_code == 200 else {}
    assert status["status"] == "failed" and "is not on this Mac" in (status.get("error") or ""), status
    assert _entities(client) == {}, "not on this Mac: the step says so and runs no other pipeline"

    assert _download(client, db)["state"] == "done"
    _names_run(client, db, [page.id], model=NAME)
    made = _entities(client)
    assert made, "the pipeline loaded from the store found names"
    assert {e["label"] for m in made.values() for e in m["attribution_chain"] if e["role"] == "extractor"} == {NAME}


def test_source_recipe_missing_model_offered(client, db, store, tmp_path):
    """source.recipe.missing-model-offered: "a step pinned to a model that is not on this Mac and can be downloaded
    (today: a spaCy pipeline) is named in the Start plan with the model and its size, and the plan offers the
    download (`downloads`, each a `download-model` job on the network lane); Start is refused until it is there"."""
    from tests.unit.recipes.test_recipe_execution_to_spec import _recipe, _save

    names = {"id": "names", "job": "find-names-tag-words", "model": {"spacy": NAME, "version": VERSION}}
    _save(client, _recipe(tmp_path, names))
    plan = client.get("/api/recipes/project/start").json()
    (offer,) = plan["downloads"]
    assert (offer["runtime"], offer["model"], offer["size_mb"]) == ("spacy", NAME, 45), offer
    assert any(NAME in r and "45 MB" in r for r in plan["refusals"]), plan["refusals"]
    assert client.post("/api/recipes/project/start").status_code == 422

    r = client.post("/api/actions/invoke", json={"name": offer["action"], "params": offer["params"]})
    assert r.status_code == 200, r.text
    job_id = r.json()["result"]["job_id"]
    end = time.monotonic() + 60
    while jobs.read_job(db, job_id)["state"] not in ("done", "failed") and time.monotonic() < end:
        time.sleep(0.1)
    assert jobs.read_job(db, job_id)["state"] == "done"
    plan = client.get("/api/recipes/project/start").json()
    assert plan["downloads"] == [] and not any(NAME in r for r in plan["refusals"]), plan
