"""Real-file regression gate for the shipped paleography ensemble."""

from __future__ import annotations

import asyncio
import os
import shutil
from difflib import SequenceMatcher
from pathlib import Path

import pytest

from tests.integration._seedlib import seed

from fichero.db import db_manager
from fichero.models import Artifact, Document, DocType, FileType, Workflow
from fichero.workflows import registry as workflow_registry
from fichero.workflows.builder import build_graph
from fichero.workflows.default_workflows import _load_preset_files
from fichero.workflows.runtime import build_initial_state, to_workflow_def

import fichero.workflows.tools  # noqa: F401


FIXTURE_DIR = Path(__file__).resolve().parents[2] / "fixtures/paleography"
MANUSCRIPT_PDF = FIXTURE_DIR / "dialogo_lengua_page_18.pdf"
EXPECTED_TRANSCRIPTION = FIXTURE_DIR / "dialogo_lengua_page_18.txt"


def _paleography_workflow():
    preset = next(
        item
        for item in _load_preset_files()
        if item["name"] == "Transcribe Paleography (Ensemble + Deep Review)"
    )
    return to_workflow_def(
        Workflow(
            id="paleography-real-manuscript-fixture",
            name=preset["name"],
            description=preset.get("description", ""),
            nodes=preset["nodes"],
            edges=preset["edges"],
            config=preset.get("config", {}),
            folder_path=preset.get("folder_path", "/"),
        )
    )


def _seed_manuscript(tmp_path: Path) -> tuple[Path, Document]:
    library_path = tmp_path / "paleography-fixture.fichero"
    seed(library_path)
    source = tmp_path / MANUSCRIPT_PDF.name
    shutil.copy2(MANUSCRIPT_PDF, source)
    document = Document(
        id="dialogo-lengua-page-18",
        name=source.name,
        path=str(source),
        doc_type=DocType.file,
        file_type=FileType.pdf,
    )
    db_manager.get_database(library_path).save(document)
    return library_path, document


def test_paleography_ensemble_runs_real_manuscript_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep real Files/Zoom/Consistency nodes while stubbing paid model calls."""
    workflow = _paleography_workflow()
    library_path, document = _seed_manuscript(tmp_path)
    drafts: list[str] = []
    review_contexts: list[object] = []

    def resolve_alias(provider: str, model: str, **_kwargs) -> tuple[str, str]:
        return ("fixture", provider or model or "fixture-model")

    async def transcribe(inputs, state, llm_config):
        assert inputs["files"]
        assert all(Path(path).is_file() for path in inputs["files"])
        text = f"draft-{len(drafts) + 1}: enel tiempo que el escriuio"
        drafts.append(text)
        return {
            "text": text,
            "records": [{"text": text} for _ in inputs["files"]],
            "value": text,
            "error": None,
        }

    async def review(inputs, state, llm_config):
        review_contexts.append(inputs.get("context"))
        text = "reviewed: enel tiempo que el escriuio"
        return {
            "text": text,
            "records": [{"text": text} for _ in inputs["files"]],
            "value": text,
            "error": None,
        }

    async def search(inputs, state, llm_config):
        return {"files": [], "documents": [], "count": 0, "error": None}

    async def translate(inputs, state, llm_config):
        return {"text": "translated manuscript", "value": "translated manuscript"}

    monkeypatch.setattr(
        "fichero.llm.resolve_model_alias_for_capability",
        resolve_alias,
    )
    monkeypatch.setitem(workflow_registry.TOOLS, "transcribe", transcribe)
    monkeypatch.setitem(workflow_registry.TOOLS, "transcribe_review", review)
    monkeypatch.setitem(workflow_registry.TOOLS, "search", search)
    monkeypatch.setitem(workflow_registry.TOOLS, "translate", translate)

    state = build_initial_state(
        {"selected_doc_ids": [document.id]},
        library_path=str(library_path),
    )
    state["workflow_id"] = workflow.id
    state["task_id"] = "paleography-real-file-deterministic"
    final_state = asyncio.run(build_graph(workflow, skip_cache=True).ainvoke(state))

    assert not final_state.get("error")
    outputs = final_state["outputs"]
    assert len(drafts) == 3
    assert outputs["t1a"]["records"]
    assert review_contexts[0] == [
        [{"text": draft}, {"text": draft}]
        for draft in drafts
    ]
    assert outputs["zoom"]["files"]
    assert all(Path(path).is_file() for path in outputs["zoom"]["files"])
    assert {"t1a", "t1b", "t1c", "t2", "t3", "t4", "consistency"} <= set(outputs)
    pages = db_manager.get_database(library_path).query(
        Document,
        parent_id=document.id,
        doc_type=DocType.page,
    )
    assert len(pages) == 1


def _real_provider_ready() -> bool:
    aliases = ("VISION_SMALL", "VISION_MEDIUM", "VISION_LARGE", "MEDIUM")
    return os.getenv("FICHERO_RUN_PALEOGRAPHY_REAL") == "1" and all(
        os.getenv(f"FICHERO_{alias}_PROVIDER")
        and os.getenv(f"FICHERO_{alias}_MODEL")
        for alias in aliases
    )


@pytest.mark.skipif(
    not _real_provider_ready(),
    reason=(
        "Set FICHERO_RUN_PALEOGRAPHY_REAL=1 and configure the vision-small, "
        "vision-medium, vision-large, and medium aliases to run paid providers"
    ),
)
def test_paleography_ensemble_real_providers(tmp_path: Path) -> None:
    """Opt-in paid gate: real manuscript, real graph, real configured models."""
    workflow = _paleography_workflow()
    library_path, document = _seed_manuscript(tmp_path)
    state = build_initial_state(
        {"selected_doc_ids": [document.id]},
        library_path=str(library_path),
    )
    state["workflow_id"] = workflow.id
    state["task_id"] = "paleography-real-provider-gate"

    final_state = asyncio.run(build_graph(workflow, skip_cache=True).ainvoke(state))

    assert not final_state.get("error")
    outputs = final_state["outputs"]
    assert all(outputs[node]["text"].strip() for node in ("t1a", "t1b", "t1c", "t2", "t3", "t4"))
    expected = EXPECTED_TRANSCRIPTION.read_text(encoding="utf-8")
    actual = outputs["t4"]["text"]
    similarity = SequenceMatcher(None, expected.casefold(), actual.casefold()).ratio()
    assert similarity >= 0.15, f"paleography output similarity too low: {similarity:.3f}"

    db = db_manager.get_database(library_path)
    pages = db.query(Document, parent_id=document.id, doc_type=DocType.page)
    assert len(pages) == 1
    assert db.query(Artifact, document_id=pages[0].id)
