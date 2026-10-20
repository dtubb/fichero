"""The rough edges an agent hit onboarding a project through MCP (#5584), tested to the spec through the routes:

* `source.project.setup-saves-what-is-sent` and `source.find.installed-readers-listed` and the
  `source.recipe.done-is-not-redone` addition for correcting and finding names
  (docs/contributor_manual/specs/source/models-chains-and-projects.md);
* `importer.folder-status-names-its-folder` (docs/contributor_manual/specs/importer/importer.md).

The other two edges are pinned on the generated surfaces: `openapi.mcp.reads-say-so` in
`fichero-mcp/tests/test_mcp_reads_say_so.py`, `openapi.cli.path-ids-positional` in
`fichero-cli/tests/test_cli_path_ids_positional.py`.
"""
from __future__ import annotations

import json
from pathlib import Path

from fichero_server.models import Artifact, DocType, Document
from fichero_server.models.knowledge import KnowledgeEntity
from tests.unit.recipes.test_recipe_execution_to_spec import (  # noqa: F401  (fixtures)
    _recipe,
    _save,
    pages,
)

GEMINI = {"cloud": "openrouter", "model": "google/gemini-3-flash-preview"}
LINES = {"id": "lines", "job": "find-lines", "model": {"kraken": "blla", "kraken_version": "bundled"}}
READ = {"id": "read", "job": "read-a-line", "model": GEMINI, "runs_on": "cloud:openrouter"}
CORRECT = {"id": "correct", "job": "correct", "model": GEMINI, "runs_on": "cloud:openrouter"}
NAMES = {"id": "names", "job": "find-names-tag-words", "model": GEMINI, "runs_on": "cloud:openrouter"}


# -- source.project.setup-saves-what-is-sent ------------------------------------------------------------------


def test_source_project_setup_saves_what_is_sent(client, db, tmp_path):
    """source.project.setup-saves-what-is-sent: "saving a project's setup ... changes only the parts sent: a part
    left out (the answers, or the recipe) is kept as it was, and a part sent as null is removed. The route's
    description says so.\""""
    answers = {"purposes": ["transcribe"], "cloud_allowed": True}
    _save(client, _recipe(tmp_path, LINES))
    first = client.get("/api/recipes/project").json()
    assert first["answers"]["cloud_allowed"] is True and first["recipe"]["steps"][0]["id"] == "lines"

    # The recipe alone: the answers saved a step before stay (what the agent lost).
    r = client.put("/api/recipes/project", json={"recipe": _recipe(tmp_path, LINES, READ)})
    assert r.status_code == 200, r.text
    saved = client.get("/api/recipes/project").json()
    assert saved["answers"] == first["answers"], "answers left out are kept"
    assert [s["id"] for s in saved["recipe"]["steps"]] == ["lines", "read"]

    # The answers alone: the recipe stays.
    r = client.put("/api/recipes/project", json={"answers": answers})
    assert r.status_code == 200, r.text
    saved = client.get("/api/recipes/project").json()
    assert saved["answers"]["purposes"] == ["transcribe"]
    assert [s["id"] for s in saved["recipe"]["steps"]] == ["lines", "read"], "a recipe left out is kept"

    # A part sent as null is removed; the other stays.
    r = client.put("/api/recipes/project", json={"recipe": None})
    assert r.status_code == 200, r.text
    saved = client.get("/api/recipes/project").json()
    assert saved["recipe"] is None and saved["answers"]["purposes"] == ["transcribe"]

    contract = json.loads((Path(__file__).resolve().parents[2] / "contracts" / "openapi.json").read_text())
    said = contract["paths"]["/api/recipes/project"]["put"]["description"]
    assert "left out" in said and "kept" in said and "null is removed" in said


# -- source.find.installed-readers-listed ---------------------------------------------------------------------


class _Store:
    """The MLX model store's catalogue: an installed vision model, an installed text model, and a vision model
    not downloaded."""

    def list_catalog_entries(self):
        from fichero_server.llm.local_inference import LocalModelCatalogEntry

        def entry(model_id, capabilities, installed):
            return LocalModelCatalogEntry(provider_type="omlx", model_id=model_id, display_name=model_id,
                                          capabilities=capabilities, installed=installed,
                                          download_size_bytes=2_000_000_000, disk_usage_bytes=1_900_000_000)

        return [entry("mlx-community/reader-vl", ["vision", "text"], True),
                entry("mlx-community/writer", ["text"], True),
                entry("mlx-community/not-here-vl", ["vision"], False)]


def test_source_find_installed_readers_listed(client, monkeypatch, tmp_path):
    """source.find.installed-readers-listed: "the local-models list ... lists the readers installed on this Mac
    beside Whisper, embeddings and spaCy: every complete MLX vision model in the model store (`model_type` `mlx`)
    and every Kraken reader downloaded or trained (`model_type` `kraken`), read from the one local catalogue
    Settings lists ... `model_type=mlx` or `kraken` narrows it to those.\""""
    from fichero_server.api.routes.ai import local_inference

    monkeypatch.setattr(local_inference, "get_mlx_model_store", lambda: _Store())
    monkeypatch.setenv("FICHERO_KRAKEN_DATA_DIR", str(tmp_path / "kraken-data"))
    markers = tmp_path / "kraken-data" / "recognition"
    markers.mkdir(parents=True)
    for reader in ("kraken-mccatmus", "kraken-zenodo-4242"):  # a shortlist reader, and one from the repository
        (markers / f"{reader}.installed").write_text("{}")

    mlx = client.get("/api/local-models", params={"model_type": "mlx"}).json()["models"]
    assert [(m["model_id"], m["model_type"], m["is_downloaded"]) for m in mlx] == \
        [("mlx-community/reader-vl", "mlx", True)], "only installed vision models: not a text model, not one not here"
    kraken = client.get("/api/local-models", params={"model_type": "kraken"}).json()["models"]
    assert {m["model_id"] for m in kraken} == {"kraken-mccatmus", "kraken-zenodo-4242"}
    assert all(m["model_type"] == "kraken" and m["download_state"] == "installed" for m in kraken)
    assert "10.5281/zenodo.4242" in next(m for m in kraken if m["model_id"] == "kraken-zenodo-4242")["display_name"]

    everything = client.get("/api/local-models").json()["models"]
    kinds = {m["model_type"] for m in everything}
    assert {"mlx", "kraken", "whisper", "embeddings"} <= kinds, kinds
    # One catalogue: Settings' list of installed Kraken readers is the same list.
    settings = {e.model_id for e in local_inference.installed_local_model_entries("kraken")}
    assert {"kraken-mccatmus", "kraken-zenodo-4242"} <= settings


# -- importer.folder-status-names-its-folder ------------------------------------------------------------------


def test_importer_folder_status_names_its_folder(client, db, tmp_path):
    """importer.folder-status-names-its-folder: "a folder import's status ... names the folder document the import
    made for the folder dropped (`folder_id`) ... Null while it runs, and for an import that made no one
    folder.\""""
    box = tmp_path / "Box 7"
    (box / "bundle").mkdir(parents=True)
    (box / "a.txt").write_text("one")
    (box / "bundle" / "b.txt").write_text("two")

    task = client.post("/api/ingest/folder", json={"path": str(box), "recursive": True}).json()
    status = client.get(f"/api/ingest/status/{task['task_id']}").json()
    assert status["status"] == "completed", status
    [folder] = [d for d in db.query(Document, name="Box 7") if d.doc_type == DocType.folder]
    assert status["folder_id"] == folder.id
    [bundle] = [d for d in db.query(Document, name="bundle") if d.doc_type == DocType.folder]
    assert bundle.parent_id == folder.id, "the folder named is the top one, not a folder inside it"

    # The same folder again: the import finds its folder already there, and names it.
    again = client.post("/api/ingest/folder", json={"path": str(box), "recursive": True}).json()
    assert client.get(f"/api/ingest/status/{again['task_id']}").json()["folder_id"] == folder.id

    # An empty folder still makes its folder, and names it.
    empty = tmp_path / "Empty box"
    empty.mkdir()
    task = client.post("/api/ingest/folder", json={"path": str(empty)}).json()
    [made] = [d for d in db.query(Document, name="Empty box") if d.doc_type == DocType.folder]
    assert client.get(f"/api/ingest/status/{task['task_id']}").json()["folder_id"] == made.id


# -- source.recipe.done-is-not-redone: correcting and finding names ---------------------------------------------


def test_source_recipe_done_is_not_redone__correcting_and_finding_names_can_tell(client, db, pages, tmp_path):  # noqa: F811
    """source.recipe.done-is-not-redone: "correcting and finding names can tell too: correcting, on a page with a
    reviewed transcription saved by the step's own model; finding names, on a page some entity names as a page it
    was found on.\""""
    _save(client, _recipe(tmp_path, LINES, READ, CORRECT, NAMES))
    plan = client.get("/api/recipes/project/start").json()
    cards = {c["job"]: c for c in plan["runs"]}
    correct, names = cards["correct"], cards["find-names-tag-words"]
    assert (correct["done"], correct["of"]) == (0, 2) and (names["done"], names["of"]) == (0, 2)
    assert "cannot tell" not in correct["note"] and "cannot tell" not in names["note"]

    first, second = pages
    model = correct.get("model_override")
    db.save(Artifact(document_id=first.id, artifact_type="transcription_review", model=model, content="leído"))
    db.save(Artifact(document_id=second.id, artifact_type="transcription_review", model="another/model",
                     content="otro"))
    db.save(KnowledgeEntity(canonical_name="Juan", source_document_ids=[second.id]))

    cards = {c["job"]: c for c in client.get("/api/recipes/project/start").json()["runs"]}
    assert (cards["correct"]["done"], cards["correct"]["of"]) == (1, 2), \
        "a page reviewed by another model is not reviewed by this one"
    assert "already done on 1 of 2 pages" in cards["correct"]["note"]
    assert (cards["find-names-tag-words"]["done"], cards["find-names-tag-words"]["of"]) == (1, 2)
