from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from fichero_server.api.routes.workflow.chains import _build_paleography_chain


def _wf(id_: str, name: str):
    return SimpleNamespace(id=id_, name=name)


def test_build_paleography_chain_matches_a_b_c_workflows():
    workflows = [
        _wf("w1", "Transcribe Manuscripts"),
        _wf("w2", "Extract Entities and NER"),
        _wf("w3", "Catalogue Synthesis"),
    ]

    chain, matched = _build_paleography_chain(workflows)
    assert matched == {"A": "w1", "B": "w2", "C": "w3"}
    assert chain.entry_step == "stage_a_transcription"
    assert [s.id for s in chain.steps] == [
        "stage_a_transcription",
        "stage_b_extract_ner",
        "stage_c_catalogue",
    ]


def test_build_paleography_chain_prefers_paleography_transcription():
    workflows = [
        _wf("generic", "Transcribe Manuscripts with OCR"),
        _wf("paleography", "Transcribe Paleography"),
        _wf("extract", "Extract Entities and NER"),
        _wf("catalogue", "Catalogue Synthesis"),
    ]

    _, matched = _build_paleography_chain(workflows)

    assert matched["A"] == "paleography"


def test_build_paleography_chain_raises_when_required_stage_missing():
    workflows = [
        _wf("w1", "Transcribe Manuscripts"),
        _wf("w2", "Extract Entities and NER"),
    ]
    with pytest.raises(HTTPException) as exc:
        _build_paleography_chain(workflows)
    assert exc.value.status_code == 400
    assert "missing workflows" in str(exc.value.detail).lower()


# ---------------------------------------------------------------------------
# #4139 / #4450 — candidates include the app's defaults, and chain steps load
# ---------------------------------------------------------------------------


def _save_workflow(db, name: str, *, is_system: bool):
    from fichero_server.models import Workflow

    workflow = Workflow(
        name=name,
        format="nodes",
        is_system=is_system,
        is_template=is_system,
        nodes=[{"id": "files-source", "tool": "files", "inputs": {}, "config": {}}],
        edges=[],
    )
    db.save(workflow)
    return workflow


@pytest.fixture
def global_db():
    from fichero_server.db.manager import db_manager
    from fichero_server.db.storage import settings

    return db_manager.get_database(str(settings.global_library_path))


class TestPreviewUsesGlobalDefaults:
    def test_preview_matches_paleography_default_from_global(
        self, client, db, global_db
    ):
        """#4139: the paleography preset in a NON-global library must see the
        shipped defaults (they live only in global.fichero, #4102). Without
        the merged candidate set the scorer falls back to the generic
        library workflow — the reported defect."""
        default = _save_workflow(global_db, "Transcribe Paleography", is_system=True)
        _save_workflow(db, "Transcribe Manuscripts with OCR", is_system=False)
        _save_workflow(db, "Extract Entities and NER", is_system=False)
        _save_workflow(db, "Catalogue Synthesis", is_system=False)

        r = client.get("/api/chains/presets/paleography")
        assert r.status_code == 200
        assert r.json()["matched_workflows"]["A"] == default.id


class TestWorkflowLoader:
    def test_loader_returns_workflow_def_for_stored_workflow(self, test_package, db):
        """#4139: the loader read `workflow.definition`, an attribute the
        Workflow model has never had, so EVERY chain step resolved to None
        and chain execution could not load any workflow."""
        from fichero_server.api.routes.workflow.chains import _create_workflow_loader

        workflow = _save_workflow(db, "Loadable Pipeline", is_system=False)
        loader = _create_workflow_loader(str(test_package))

        definition = loader(workflow.id)
        assert definition is not None
        assert definition.id == workflow.id
        assert [n.tool for n in definition.nodes] == ["files"]

    def test_loader_resolves_global_default(self, test_package, global_db):
        """A chain step referencing a shipped default runs in any library."""
        from fichero_server.api.routes.workflow.chains import _create_workflow_loader

        default = _save_workflow(global_db, "Default Step", is_system=True)
        loader = _create_workflow_loader(str(test_package))

        definition = loader(default.id)
        assert definition is not None
        assert definition.id == default.id

    def test_loader_returns_none_for_unknown_id(self, test_package):
        from fichero_server.api.routes.workflow.chains import _create_workflow_loader

        loader = _create_workflow_loader(str(test_package))
        assert loader("no-such-workflow") is None
