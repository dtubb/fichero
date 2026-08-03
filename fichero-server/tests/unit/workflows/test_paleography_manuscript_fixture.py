"""Real-file regression gate for the shipped paleography ensemble."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
from pathlib import Path

import pytest

from tests.integration._seedlib import seed

from fichero_server.db import db_manager
from fichero_server.models import Artifact, Document, DocType, FileType, Workflow
from fichero_server.workflows import registry as workflow_registry
from fichero_server.workflows.builder import build_graph
from fichero_server.workflows.default_workflows import _load_preset_files
from fichero_server.workflows.runtime import build_initial_state, to_workflow_def
from fichero_server.workflows.transcription_accuracy import (
    ACCENT_BLIND,
    DIPLOMATIC,
    LAYOUT_INSENSITIVE,
    LENIENT,
    score_texts_under_policies,
)

import fichero_server.workflows.tools  # noqa: F401


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

    monkeypatch.setattr(
        "fichero_server.llm.resolve_model_alias_for_capability",
        resolve_alias,
    )
    monkeypatch.setitem(workflow_registry.TOOLS, "transcribe", transcribe)
    monkeypatch.setitem(workflow_registry.TOOLS, "transcribe_review", review)
    monkeypatch.setitem(workflow_registry.TOOLS, "search", search)

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
    assert {"t1a", "t1b", "t1c", "t2", "t3", "t4"} <= set(outputs)
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
    # #3905 wants a recorded character error rate against the DILE gold, not a
    # similarity ratio. `difflib` does not compute a minimal edit distance, and
    # the old floor of 0.15 with an unlabelled case-fold would have passed on
    # almost any page of Spanish. Report every tier under every policy so a run
    # of this gate IS the calibration measurement, then fail only on numbers
    # that mean "this is not a transcription of this page".
    expected = EXPECTED_TRANSCRIPTION.read_text(encoding="utf-8")
    policies = [DIPLOMATIC, LAYOUT_INSENSITIVE, LENIENT, ACCENT_BLIND]
    recorded: dict[str, dict[str, float]] = {}
    for node in ("t1a", "t1b", "t1c", "t2", "t3", "t4"):
        recorded[node] = {
            score.policy: round(score.cer, 4)
            for score in score_texts_under_policies(
                expected, outputs[node]["text"], policies
            )
        }
    print("paleography CER by tier and policy:", json.dumps(recorded, indent=2))

    final = recorded["t4"]
    assert final[ACCENT_BLIND.name] < 0.5, (
        "the ensemble's final pass is more than half wrong on this page even "
        f"with accents, case and punctuation folded away: {recorded['t4']}"
    )

    db = db_manager.get_database(library_path)
    pages = db.query(Document, parent_id=document.id, doc_type=DocType.page)
    assert len(pages) == 1
    assert db.query(Artifact, document_id=pages[0].id)
