"""Step 3.3 (#3907): one Translate preset that double-checks by default; the old ones still resolve.

`workflows.defaults.translate-crosschecks-by-default`: Translate, Translate + Double-Check and Translate (DeepL) were
three presets; Translate now runs the double-check pass, and the two names (and ids, and file keys) that went away still
find it, so a saved project, a recipe or an old run that names one keeps working.
"""

from __future__ import annotations

import json

import pytest

from fichero_server.workflows.default_workflows import (
    _load_preset_files,
    preset_workflow_id,
    resolve_shipped_workflow,
    seed_default_workflows,
    shipped_preset,
)

GONE = ("Translate + Double-Check", "Translate (DeepL)")


def test_translate_double_checks_by_default_and_the_two_others_are_gone():
    presets = {p["name"]: p for p in _load_preset_files()}
    assert not any(name in presets for name in GONE)
    order = [n["tool"] for n in presets["Translate"]["nodes"]]
    assert order == ["files", "transcribe", "text_translate", "text_translate_review"]
    review = next(n for n in presets["Translate"]["nodes"] if n["tool"] == "text_translate_review")
    assert {e["source"] for e in presets["Translate"]["edges"] if e["target"] == review["id"]} == {"text_translate"}


@pytest.fixture
def library(tmp_path, monkeypatch):
    from tests.integration._seedlib import seed

    from fichero_server.db import db_manager

    monkeypatch.setenv("FICHERO_SKIP_DEFAULT_WORKFLOWS", "1")
    path = tmp_path / "t.fichero"
    seed(path)
    db = db_manager.get_database(path)
    seed_default_workflows(db)
    yield db
    db_manager.close_database(path)


@pytest.mark.parametrize("old", GONE)
def test_a_removed_presets_old_id_and_name_resolve_to_translate(library, old):
    by_id = resolve_shipped_workflow(library, preset_workflow_id(old), old)
    assert by_id is not None and by_id.name == "Translate"
    assert any(n["tool"] == "text_translate_review" for n in by_id.nodes), "the merged preset, with its double-check"


@pytest.mark.parametrize("key", ["translate_review", "translate_deepl"])
def test_a_removed_file_key_still_finds_the_preset(key):
    found = shipped_preset(key)
    assert found is not None and found["name"] == "Translate"
    assert json.dumps(found) == json.dumps(shipped_preset("translate"))


def test_extract_presets_end_with_a_consistency_check_fed_by_the_table():
    """`workflows.defaults.extraction-has-consistency-pass` (#3909): Extract Table and Accounts → Spreadsheet flag a figure that
    disagrees with its words and a name spelled two ways, from the table's own text; the check calls no model."""
    from fichero_server.workflows.registry import get_tool_def

    assert get_tool_def("consistency-check").uses_llm is False
    presets = {p["name"]: p for p in _load_preset_files()}
    for name in ("Extract Table", "Accounts → Spreadsheet (CSV)"):
        nodes = presets[name]["nodes"]
        assert [n["tool"] for n in nodes] == ["files", "table_extract", "consistency-check"], name
        table = next(n["id"] for n in nodes if n["tool"] == "table_extract")
        check = next(n["id"] for n in nodes if n["tool"] == "consistency-check")
        assert any(e["source"] == table and e["target"] == check and e["source_port"] == "text" and e["target_port"] == "text"
                   for e in presets[name]["edges"]), name


def test_translate_from_an_artifact_menu_runs_against_the_library_that_owns_the_document(tmp_path, monkeypatch):
    """`workflows.translate-from-artifact-menu-runs` (#4306): `artifact.translate` works on the db it is handed, so a document in a
    project (not the global library) is found and translated, from the worker thread a sync route uses; a document that is not in that db is a clear 404, never a crash.
    The app half (the owning library, matched by service identity) is pinned by DocumentScopeGuardTests."""
    from fastapi import HTTPException

    from fichero_server.actions.registry import ActionContext
    from fichero_server.api.routes.document import artifacts as routes
    from fichero_server.db import db_manager
    from fichero_server.models import Artifact, Document, DocType
    from tests.integration._seedlib import seed

    monkeypatch.setenv("FICHERO_SKIP_DEFAULT_WORKFLOWS", "1")

    async def fake_translate(text, **kwargs):
        return "translated: " + text

    monkeypatch.setattr("fichero_server.llm.translate_text", fake_translate)
    path = tmp_path / "project.fichero"
    seed(path)
    db = db_manager.get_database(path)
    try:
        db.save(Document(id="d1", name="d1", doc_type=DocType.page, page_content="hola"))
        monkeypatch.setattr(db, "embed_artifact_content", lambda *a, **k: None)
        ctx = ActionContext(library_path=str(path))
        # A sync action runs on a worker thread with no event loop; that is where it used to raise (#4306).
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            result, spec = pool.submit(
                routes._action_translate, db, routes.ArtifactTranslateParams(document_id="d1", target_lang="en"), ctx
            ).result()
        assert result["content"] == "translated: hola" and spec.document_ids == ["d1"]
        assert db.get(Artifact, result["id"]) is not None

        with pytest.raises(HTTPException) as gone:
            routes._action_translate(db, routes.ArtifactTranslateParams(document_id="elsewhere", target_lang="en"), ctx)
        assert gone.value.status_code == 404
    finally:
        db_manager.close_database(path)
