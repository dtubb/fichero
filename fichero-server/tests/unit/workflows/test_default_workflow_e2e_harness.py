"""End-to-end default workflow regression harness (#1287).

The point is not to unit-test individual tools. It is to run the shipped
default workflow JSON through the real graph runtime and assert durable
outcomes in the seeded library: artifacts plus KG rows. This catches the
#1285 class where the graph can appear to complete while the KG handoff is
empty or disconnected.

Twostage test (#1285 re-open): The folder-catalogue path uses Apple
Intelligence → extraction_mode=twostage. The _run_two_stage function had
a bug where kg_payload.append() was guarded by `and db`. When the inline DB
open fails the payload was never built → kg_writer no-op → 0 rows. Fixed by
changing the guard to `and container` and moving `and db` down to protect
only the inline _write_kg_rows call. The twostage test reproduces the failure
condition by patching db_manager inside extract_all.py while leaving the
catalogue.py and kg_writer.py db_managers unaffected.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Literal

import pytest

from tests.integration._seedlib import seed

from fichero_server.db import Database, db_manager
from fichero_server.models.knowledge import KnowledgeClaim, KnowledgeEntity
from fichero_server.models import Artifact, DocType, Document, FileType, Workflow
from fichero_server.workflows.builder import build_graph
from fichero_server.workflows.default_workflows import _load_preset_files
from fichero_server.workflows import registry as workflow_registry
from fichero_server.workflows.runtime import build_initial_state, create_compiled_app, to_workflow_def

# Import workflow tools for registry side effects before build_graph().
import fichero_server.workflows.tools  # noqa: F401
import fichero_server.workflows.tools.extract_all as extract_all_module


FIXTURE_TEXT = (
    "Regression Person signed the fixture deed in Regression Place in 1842."
)

_TRANSCRIBE_TERMINALS = {
    "Transcribe": ("transcribe",),
    "Transcribe Manuscript": ("transcribe",),
    "Transcribe Typescript": ("transcribe",),
    "Transcribe HTR": ("transcribe_review",),
    "Transcribe (Auto-Detect)": ("transcribe-ts",),
    "Transcribe Spanish Script (19th-20th C.)": ("spanish-script-v2",),
}

_TRANSLATE_TERMINALS = {
    "Translate": ("text_translate",),
    "Translate (DeepL)": ("translate",),
    "Translate + Double-Check": ("text_translate", "text_translate_review"),
}

_SPECIAL_OUTPUT_ASSERTIONS = {
    "Transcribe Paleography (Ensemble + Deep Review)",
    *_TRANSCRIBE_TERMINALS,
    *_TRANSLATE_TERMINALS,
}

# Terminal tools without declared ports cannot expose a value through the graph.
_TERMINAL_OUTPUT_EXCEPTIONS: dict[str, str] = {}


@pytest.mark.parametrize("selection_shape", ["folder", "file"])
def test_catalogue_default_workflow_lands_artifacts_and_kg_rows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    selection_shape: Literal["folder", "file"],
):
    """Run the unmodified default Catalogue preset for folder and file shapes."""

    _install_deterministic_workflow_stubs(monkeypatch)
    library_path, selected_doc_id, source_doc_id, catalogue_target_id = _seed_fixture_library(
        tmp_path,
        selection_shape=selection_shape,
    )
    db = db_manager.get_database(library_path)

    before_claims = len(db.all(KnowledgeClaim))
    before_entities = len(db.all(KnowledgeEntity))

    workflow = _load_catalogue_workflow()
    state = build_initial_state(
        {"selected_doc_ids": [selected_doc_id]},
        library_path=str(library_path),
    )
    state["workflow_id"] = workflow.id
    state["task_id"] = f"test-{selection_shape}-catalogue"

    final_state = asyncio.run(build_graph(workflow, skip_cache=True).ainvoke(state))

    _assert_workflow_completed(final_state)
    _assert_artifacts_landed(
        db,
        catalogue_target_id=catalogue_target_id,
        source_doc_id=source_doc_id,
    )
    _assert_kg_rows_landed(
        db,
        source_doc_id=source_doc_id,
        before_entities=before_entities,
        before_claims=before_claims,
    )


def test_catalogue_default_workflow_processes_imported_pdf_page_children(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """Imported PDF page children should receive artifacts and KG claims."""

    _install_deterministic_workflow_stubs(monkeypatch)
    library_path, parent_doc_id, page_doc_ids = _seed_imported_pdf_page_library(tmp_path)
    db = db_manager.get_database(library_path)

    before_claims = len(db.all(KnowledgeClaim))
    before_entities = len(db.all(KnowledgeEntity))

    workflow = _load_catalogue_workflow()
    state = build_initial_state(
        {"selected_doc_ids": [parent_doc_id]},
        library_path=str(library_path),
    )
    state["workflow_id"] = workflow.id
    state["task_id"] = "test-imported-pdf-page-catalogue"

    final_state = asyncio.run(build_graph(workflow, skip_cache=True).ainvoke(state))

    _assert_workflow_completed(final_state)
    parent_doc = db.get(Document, parent_doc_id)
    assert parent_doc is not None
    assert parent_doc.page_content == "Catalogue narrative for the regression fixture."

    assert len(db.all(KnowledgeEntity)) > before_entities
    assert len(db.all(KnowledgeClaim)) > before_claims
    for page_doc_id in page_doc_ids:
        artifacts = db.query(Artifact, document_id=page_doc_id)
        assert any(a.artifact_type == "transcription" for a in artifacts)
        assert any(a.artifact_type == "people" for a in artifacts)

        claims = db.query(KnowledgeClaim, source_document_id=page_doc_id)
        assert any(
            claim.text == "Regression Person signed the fixture deed."
            and claim.entity_ids
            for claim in claims
        )


def test_catalogue_live_graph_waits_for_all_merge_inputs_before_catalogue(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """#1665: live/checkpointed execution must not catalogue before extraction ends."""

    _install_deterministic_workflow_stubs(monkeypatch)
    library_path, parent_doc_id, _page_doc_ids = _seed_imported_pdf_page_library(tmp_path)
    db = db_manager.get_database(library_path)
    workflow = _load_catalogue_workflow()
    app, checkpointer = create_compiled_app(
        workflow,
        db_path=db.path,
        enable_parallel=True,
        skip_cache=True,
    )
    state = build_initial_state(
        {"selected_doc_ids": [parent_doc_id]},
        library_path=str(library_path),
    )
    state["workflow_id"] = workflow.id
    state["task_id"] = "test-live-catalogue-fanin"
    config = {"configurable": {"thread_id": "test-live-catalogue-fanin"}}

    events: list[tuple[str, str]] = []

    async def run() -> dict:
        async for event in app.astream_events(state, config=config, version="v2"):
            kind = event.get("event")
            name = event.get("name")
            if (
                kind in {"on_chain_start", "on_chain_end"}
                and isinstance(name, str)
                and name not in {"__start__", "LangGraph"}
                and not name.startswith("Runnable")
            ):
                events.append((kind, name))
        checkpoint = await checkpointer.aget_tuple(config)
        assert checkpoint is not None
        return checkpoint.checkpoint.get("channel_values", {})

    final_state = asyncio.run(run())
    _assert_workflow_completed(final_state)

    def event_index(kind: str, name: str) -> int:
        try:
            return events.index((kind, name))
        except ValueError as exc:  # pragma: no cover - assertion message path
            raise AssertionError(f"missing event {(kind, name)!r} in {events!r}") from exc

    catalogue_start = event_index("on_chain_start", "Catalogue")
    assert event_index("on_chain_end", "Extract All Entities") < catalogue_start
    assert ("on_chain_end", "Write KG") not in events


@pytest.mark.parametrize(
    "preset_name",
    [p["name"] for p in _load_preset_files()],
)
def test_all_default_workflows_complete_with_deterministic_tool_stubs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    preset_name: str,
):
    """Smoke-run every shipped default workflow JSON to completion.

    This is the broad CI guard for #1287: if a preset JSON wiring change
    introduces a graph/runtime regression, this test fails even when single
    tool unit tests still pass.
    """
    seed(tmp_path / "all-defaults-smoke.fichero")
    workflow = _load_workflow_by_name(preset_name)
    _install_generic_tool_smoke_stubs(monkeypatch, workflow)

    state = build_initial_state(
        {"selected_doc_ids": ["stub-doc-1"]},
        library_path=str(tmp_path / "all-defaults-smoke.fichero"),
    )
    state["workflow_id"] = workflow.id
    state["task_id"] = f"default-smoke-{preset_name.lower().replace(' ', '-')}"

    final_state = asyncio.run(
        build_graph(
            workflow,
            enable_parallel=preset_name != "Transcribe (Auto-Detect)",
            skip_cache=True,
        ).ainvoke(state)
    )
    assert not final_state.get("error"), (preset_name, final_state.get("error"))
    completed = set(final_state.get("completed_nodes") or [])
    expected = _expected_completed_nodes_for_smoke(workflow)
    assert expected <= completed, (
        f"{preset_name}: expected all nodes completed; missing={sorted(expected - completed)}"
    )
    if preset_name == "Transcribe Paleography (Ensemble + Deep Review)":
        _assert_paleography_ensemble_flow(final_state)
    if preset_name in _TRANSCRIBE_TERMINALS:
        _assert_transcribe_terminal_outputs(final_state, _TRANSCRIBE_TERMINALS[preset_name])
    if preset_name in _TRANSLATE_TERMINALS:
        _assert_translate_terminal_outputs(final_state, _TRANSLATE_TERMINALS[preset_name])
    if preset_name not in _SPECIAL_OUTPUT_ASSERTIONS:
        _assert_declared_terminal_outputs(workflow, final_state, preset_name)


def _install_deterministic_workflow_stubs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep CI deterministic while preserving workflow data flow."""

    def resolve_alias(provider: str, model: str) -> tuple[str, str]:
        if (provider or "").startswith("$"):
            return ("fake", "fake-model")
        return (provider, model)

    async def fake_extract_all_structured(**kwargs):
        schema = kwargs.get("schema")
        if schema is not extract_all_module._Extraction:
            raise AssertionError(f"unexpected structured schema: {schema!r}")
        return extract_all_module._Extraction(
            people=[
                extract_all_module._Person(
                    name="Regression Person",
                    verb="signed",
                    object="the fixture deed",
                    source_text="Regression Person signed the fixture deed",
                )
            ],
            places=[
                extract_all_module._Place(
                    name="Regression Place",
                    verb="hosted",
                    object="the fixture signing",
                    source_text="in Regression Place",
                )
            ],
            organizations=[],
            dates=[
                extract_all_module._DateItem(
                    date="1842",
                    date_normalized="1842",
                    verb="dated",
                    object="the fixture deed",
                    source_text="in 1842",
                )
            ],
            events=[],
            quotes=[],
            keywords=["regression fixture"],
        )

    async def fake_resumen(*args, **kwargs):
        return ("Catalogue narrative for the regression fixture.", [])

    async def fake_keywords(*args, **kwargs):
        return "regression fixture; workflow harness"

    async def fake_citations_extract(*args, **kwargs):
        return {"text": "", "value": [], "cached": False}

    monkeypatch.setattr("fichero_server.llm.resolve_model_alias", resolve_alias)
    monkeypatch.setattr(
        "fichero_server.workflows.tools.extract_all.chat_structured_with_fallback",
        fake_extract_all_structured,
    )
    monkeypatch.setattr(
        "fichero_server.workflows.tools.catalogue._generate_resumen",
        fake_resumen,
    )
    monkeypatch.setattr(
        "fichero_server.workflows.tools.catalogue._generate_keywords",
        fake_keywords,
    )
    monkeypatch.setattr(
        "fichero_server.workflows.tools.citations_extract.citations_extract",
        fake_citations_extract,
    )
    monkeypatch.setitem(
        workflow_registry.TOOLS,
        "citations_extract",
        fake_citations_extract,
    )
    async def _noop_cleanup(*args, **kwargs):
        state = kwargs.get("state") or {}
        assert "extract_all" in (state.get("outputs") or {}), (
            "folder cleanup must not run before extract_all output exists"
        )
        return {"text": "", "value": [], "cached": False}
    for _tool in (
        "people_folder_cleanup",
        "places_folder_cleanup",
        "organizations_folder_cleanup",
        "dates_folder_cleanup",
        "events_folder_cleanup",
        "keywords_folder_cleanup",
    ):
        monkeypatch.setitem(workflow_registry.TOOLS, _tool, _noop_cleanup)
    monkeypatch.setattr(Database, "embed", lambda *args, **kwargs: False)
    monkeypatch.setattr(
        "fichero_server.kg.entity_vectors.find_similar",
        lambda *args, **kwargs: [],
    )
    monkeypatch.setattr(
        "fichero_server.kg.entity_vectors.index_entity",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "fichero_server.kg.rebuild.rebuild_kg",
        lambda *args, **kwargs: {
            "entities": 0,
            "claims": 0,
            "triples_written": 0,
        },
    )


def _seed_fixture_library(
    tmp_path: Path,
    *,
    selection_shape: Literal["folder", "file"],
) -> tuple[Path, str, str, str]:
    library_path = tmp_path / f"{selection_shape}.fichero"
    seed(library_path)
    db = db_manager.get_database(library_path)

    source_file = tmp_path / f"{selection_shape}-fixture.txt"
    source_file.write_text(FIXTURE_TEXT, encoding="utf-8")

    folder = Document(
        id=f"workflow-{selection_shape}-folder",
        name=f"Workflow {selection_shape} fixture",
        doc_type=DocType.folder,
    )
    source_doc = Document(
        id=f"workflow-{selection_shape}-doc",
        parent_id=folder.id,
        name=source_file.name,
        path=str(source_file),
        doc_type=DocType.file,
        file_type=FileType.text,
    )
    db.save(folder)
    db.save(source_doc)

    selected_doc_id = folder.id if selection_shape == "folder" else source_doc.id
    # After #1291, _resolve_container_doc returns the file itself for a single-file
    # selection (not the enclosing folder). Mirror that resolution here so assertions
    # query the doc that catalogue actually writes to.
    catalogue_target_id = folder.id if selection_shape == "folder" else source_doc.id
    return library_path, selected_doc_id, source_doc.id, catalogue_target_id


def _seed_imported_pdf_page_library(tmp_path: Path) -> tuple[Path, str, list[str]]:
    library_path = tmp_path / "imported-pages.fichero"
    seed(library_path)
    db = db_manager.get_database(library_path)

    source_file = tmp_path / "marshall-imported.pdf"
    source_file.write_bytes(b"%PDF-1.4\n% regression fixture\n")

    parent_doc = Document(
        id="marshall-imported-pdf",
        name="Marshall imported PDF",
        path=str(source_file),
        doc_type=DocType.file,
        file_type=FileType.pdf,
    )
    pages = [
        Document(
            id="marshall-imported-page-1",
            parent_id=parent_doc.id,
            name="Marshall imported PDF p. 1",
            doc_type=DocType.page,
            sequence=1,
            page_content=FIXTURE_TEXT,
            metadata={
                "page_number": 1,
                "transcription": FIXTURE_TEXT,
                "text_length": len(FIXTURE_TEXT),
            },
        ),
        Document(
            id="marshall-imported-page-2",
            parent_id=parent_doc.id,
            name="Marshall imported PDF p. 2",
            doc_type=DocType.page,
            sequence=2,
            page_content=FIXTURE_TEXT,
            metadata={
                "page_number": 2,
                "transcription": FIXTURE_TEXT,
                "text_length": len(FIXTURE_TEXT),
            },
        ),
    ]
    db.save(parent_doc)
    for page in pages:
        db.save(page)

    return library_path, parent_doc.id, [page.id for page in pages]


def _load_catalogue_workflow():
    preset = next(p for p in _load_preset_files() if p["name"] == "Catalogue")
    return to_workflow_def(
        Workflow(
            id="default-catalogue-regression-harness",
            name=preset["name"],
            description=preset.get("description", ""),
            nodes=preset["nodes"],
            edges=preset["edges"],
            config=preset.get("config", {}),
            folder_path=preset.get("folder_path", "/"),
        )
    )


def _load_workflow_by_name(name: str):
    preset = next(p for p in _load_preset_files() if p["name"] == name)
    return to_workflow_def(
        Workflow(
            id=f"default-{name.lower().replace(' ', '-')}-regression-harness",
            name=preset["name"],
            description=preset.get("description", ""),
            nodes=preset["nodes"],
            edges=preset["edges"],
            config=preset.get("config", {}),
            folder_path=preset.get("folder_path", "/"),
        )
    )


def _install_generic_tool_smoke_stubs(
    monkeypatch: pytest.MonkeyPatch,
    workflow,
) -> None:
    """Stub every tool used by a workflow with a deterministic async no-op."""

    def resolve_alias(provider: str, model: str) -> tuple[str, str]:
        if (provider or "").startswith("$"):
            return ("fake", "fake-model")
        return (provider, model)

    def _stub_for(tool_name: str):
        async def _stub(inputs, state, llm_config):
            text = f"{tool_name} output"
            # Include the common payload keys consumed by downstream defaults.
            payload = {
                "value": text,
                "text": text,
                "summary": text,
                "script_type": "typescript",
                "records": [{"doc_id": "stub-doc-1", "text": text}],
                "documents": [{"id": "stub-doc-1", "name": "stub.txt"}],
                "files": ["/tmp/stub.txt"],
                "doc_ids": ["stub-doc-1"],
                "file_paths": ["/tmp/stub.txt"],
                "count": 1,
                "inconsistencies": [],
                "kg_payload": [
                    {
                        "entity_name": "Regression Person",
                        "entity_type": "person",
                        "claim": "Regression Person signed the fixture deed.",
                        "source_document_id": "stub-doc-1",
                    }
                ],
            }
            # Source-node friendliness.
            if tool_name in {"files", "folder", "collection"}:
                payload["selected_doc_ids"] = ["stub-doc-1"]
            tool_def = workflow_registry.get_tool_def(tool_name)
            if tool_def:
                for port in tool_def.output_ports:
                    payload.setdefault(port.id, text)
            return payload

        return _stub

    monkeypatch.setattr("fichero_server.llm.resolve_model_alias", resolve_alias)
    for node in workflow.nodes:
        monkeypatch.setitem(workflow_registry.TOOLS, node.tool, _stub_for(node.tool))


def _expected_completed_nodes_for_smoke(workflow) -> set[str]:
    route_targets = {
        target
        for edge in workflow.edges
        for target in ((edge.route_map or {}).values())
    }
    branch_only = set(route_targets)
    changed = True
    while changed:
        changed = False
        for edge in workflow.edges:
            if edge.route_map:
                continue
            if edge.source in branch_only and edge.target not in branch_only:
                branch_only.add(edge.target)
                changed = True
    return {node.id for node in workflow.nodes if node.id not in branch_only}


def _assert_paleography_ensemble_flow(final_state: dict) -> None:
    """The ensemble's zoomed drafts must reach both review stages (#3905)."""
    outputs = final_state.get("outputs") or {}
    assert {"zoom", "t1a", "t1b", "t1c", "t2", "t3", "t4"} <= set(outputs)
    assert outputs["zoom"]["files"]
    assert all(outputs[node]["text"] for node in ("t1a", "t1b", "t1c", "t2", "t3", "t4"))


def _assert_transcribe_terminal_outputs(final_state: dict, node_ids: tuple[str, ...]) -> None:
    """Every transcribe-family preset must finish with transcription text."""
    outputs = final_state.get("outputs") or {}
    for node_id in node_ids:
        assert outputs.get(node_id, {}).get("text"), f"{node_id} emitted no text"


def _assert_translate_terminal_outputs(final_state: dict, node_ids: tuple[str, ...]) -> None:
    """Every translate-family preset must finish with translated text (#3907)."""
    outputs = final_state.get("outputs") or {}
    for node_id in node_ids:
        assert outputs.get(node_id, {}).get("text"), f"{node_id} emitted no text"


def _assert_declared_terminal_outputs(workflow, final_state: dict, preset_name: str) -> None:
    """Every non-family preset exposes one declared terminal output (#3803)."""
    if preset_name in _TERMINAL_OUTPUT_EXCEPTIONS:
        return
    sources = {edge.source for edge in workflow.edges}
    outputs = final_state.get("outputs") or {}
    for node in (node for node in workflow.nodes if node.id not in sources):
        tool_def = workflow_registry.get_tool_def(node.tool)
        assert tool_def and tool_def.output_ports, f"{preset_name}: {node.id} has no declared output port"
        node_output = outputs.get(node.id) or {}
        assert any(node_output.get(port.id) for port in tool_def.output_ports), (
            f"{preset_name}: terminal {node.id} emitted no declared output"
        )


def _assert_workflow_completed(final_state: dict) -> None:
    serialized = repr(final_state)
    assert final_state.get("error") in (None, ""), final_state.get("error")
    assert "No KG payload" not in serialized

    completed = set(final_state.get("completed_nodes") or [])
    assert {
        "files-source",
        "transcribe",
        "extract_all",
        "catalogue",
    } <= completed

    extract_output = (final_state.get("outputs") or {}).get("extract_all") or {}
    assert extract_output.get("kg_payload"), "extract_all emitted no kg_payload"
    assert "kg_writer" not in completed


def _assert_artifacts_landed(
    db,
    *,
    catalogue_target_id: str,
    source_doc_id: str,
) -> None:
    source_artifacts = db.query(Artifact, document_id=source_doc_id)
    assert any(a.artifact_type == "transcription" for a in source_artifacts)
    assert any(a.artifact_type == "people" for a in source_artifacts)

    target_artifacts = db.query(Artifact, document_id=catalogue_target_id)
    assert any(a.artifact_type == "catalogue.narrative" for a in target_artifacts)

    target_doc = db.get(Document, catalogue_target_id)
    assert target_doc is not None
    assert target_doc.page_content == "Catalogue narrative for the regression fixture."

    if catalogue_target_id != source_doc_id:
        # Folder shape: catalogue writes to the folder, so the source file
        # retains its transcribed text in page_content.
        source_doc = db.get(Document, source_doc_id)
        assert source_doc is not None
        assert source_doc.page_content == FIXTURE_TEXT
    # File shape (#1291): catalogue writes its narrative directly onto the
    # selected file (which is the resolved container), so page_content on
    # the source doc has already been updated to the narrative above.


def _assert_kg_rows_landed(
    db,
    *,
    source_doc_id: str,
    before_entities: int,
    before_claims: int,
) -> None:
    entities = db.all(KnowledgeEntity)
    claims = db.all(KnowledgeClaim)
    assert len(entities) > before_entities
    assert len(claims) > before_claims

    names = {entity.canonical_name for entity in entities}
    assert {"Regression Person", "Regression Place", "regression fixture"} <= names

    fixture_claims = db.query(KnowledgeClaim, source_document_id=source_doc_id)
    claim_texts = {claim.text for claim in fixture_claims}
    assert "Regression Person signed the fixture deed." in claim_texts
    assert any(claim.entity_ids for claim in fixture_claims)

    # #1470/#1471 backend probe contract:
    # - timeline path needs parsed temporal fields on extracted date claims
    # - map path needs structured place_values on extracted place claims
    date_claims = [
        claim
        for claim in fixture_claims
        if (
            (claim.metadata or {}).get("date_normalized")
            or "1842" in (claim.text or "")
        )
    ]
    assert date_claims, "expected at least one extracted date claim in fixture output"
    assert any(
        claim.time_start or claim.time_end or claim.date_values
        for claim in date_claims
    ), "date claims missing parsed temporal fields (time_start/time_end/date_values)"

    place_claims = [
        claim
        for claim in fixture_claims
        if "Regression Place" in (claim.text or "")
    ]
    assert place_claims, "expected at least one extracted place claim in fixture output"
    assert any(
        claim.claim_location or claim.place_values
        for claim in place_claims
    ), "place claims missing spatial fields (claim_location/place_values)"


# ---------------------------------------------------------------------------
# Twostage-path harness (#1285 re-open)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("selection_shape", ["folder", "file"])
def test_catalogue_twostage_workflow_lands_kg_rows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    selection_shape: Literal["folder", "file"],
):
    """Twostage extraction path (Apple Intelligence default) must land KG rows."""
    _install_twostage_stubs(monkeypatch)
    library_path, selected_doc_id, source_doc_id, catalogue_target_id = _seed_fixture_library(
        tmp_path,
        selection_shape=selection_shape,
    )
    db = db_manager.get_database(library_path)

    before_claims = len(db.all(KnowledgeClaim))
    before_entities = len(db.all(KnowledgeEntity))

    workflow = _load_catalogue_workflow_twostage()
    state = build_initial_state(
        {"selected_doc_ids": [selected_doc_id]},
        library_path=str(library_path),
    )
    state["workflow_id"] = workflow.id
    state["task_id"] = f"test-{selection_shape}-catalogue-twostage"

    final_state = asyncio.run(build_graph(workflow, skip_cache=True).ainvoke(state))

    _assert_workflow_completed(final_state)
    _assert_twostage_kg_rows_landed(
        db,
        catalogue_target_id=catalogue_target_id,
        before_entities=before_entities,
        before_claims=before_claims,
    )


def _install_twostage_stubs(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stubs for the twostage extraction path that expose the #1285 bug.

    Key design:
    - Stage 1 (chat_structured_with_fallback with _EntitiesOnly) and
      Stage 2 (chat_structured with _EntityClaims) are stubbed with
      deterministic fixture entities.
    """

    async def fake_twostage_structured(**kwargs):
        """Handles both Stage 1 (_EntitiesOnly) and Stage 2 (_EntityClaims).

        Both stages call chat_structured_with_fallback; the schema arg
        distinguishes which stage is running.
        """
        schema = kwargs.get("schema")
        if schema is extract_all_module._EntitiesOnly:
            # Stage 1: entity NER pass
            return extract_all_module._EntitiesOnly(
                people=[
                    extract_all_module._EntityOnly(
                        name="Regression Person",
                        entity_type="person",
                    )
                ],
                places=[
                    extract_all_module._EntityOnly(
                        name="Regression Place",
                        entity_type="place",
                    )
                ],
                dates=[
                    extract_all_module._EntityOnly(
                        name="1842",
                        entity_type="date",
                    )
                ],
                organizations=[],
                events=[],
            )
        if schema is extract_all_module._EntityClaims:
            # Stage 2: per-entity SVO claim pass
            return extract_all_module._EntityClaims(
                subject="Regression Person",
                claims=[
                    extract_all_module._SVOClaim(
                        subject="Regression Person",
                        verb="signed",
                        object="the fixture deed",
                        source_text="Regression Person signed the fixture deed",
                        epistemic_status="established",
                        claim_type="action",
                    )
                ],
            )
        raise AssertionError(f"unexpected schema in twostage stub: {schema!r}")

    async def fake_resumen(*args, **kwargs):
        return ("Catalogue narrative for the regression fixture.", [])

    async def fake_keywords(*args, **kwargs):
        return "regression fixture; workflow harness"

    async def fake_process_vision(**kwargs):
        """Deterministic transcribe output carrying records with doc_id."""
        docs = kwargs.get("documents") or []
        records = []
        texts = []
        for index, doc in enumerate(docs):
            if not isinstance(doc, dict):
                continue
            doc_id = str(doc.get("id") or "")
            if not doc_id:
                continue
            text = (
                f"Regression Person signed fixture page {index + 1} "
                f"in Regression Place in 1842."
            )
            records.append({"doc_id": doc_id, "text": text})
            texts.append(text)
        joined = "\n\n".join(texts)
        return {
            "text": joined,
            "value": joined,
            "texts": texts,
            "values": texts,
            "results": [{"text": t, "error": None} for t in texts],
            "records": records,
            "page_records": records,
            "artifacts": [],
            "output_files": [],
            "error": None,
        }

    def resolve_alias(provider: str, model: str) -> tuple[str, str]:
        if (provider or "").startswith("$"):
            return ("fake", "fake-model")
        return (provider, model)

    monkeypatch.setattr("fichero_server.llm.resolve_model_alias", resolve_alias)
    monkeypatch.setattr(
        "fichero_server.workflows.tools.extract_all.chat_structured_with_fallback",
        fake_twostage_structured,
    )
    monkeypatch.setattr(
        "fichero_server.workflows.tools.catalogue._generate_resumen",
        fake_resumen,
    )
    monkeypatch.setattr(
        "fichero_server.workflows.tools.catalogue._generate_keywords",
        fake_keywords,
    )
    monkeypatch.setattr(
        "fichero_server.workflows.tools.transcribe.process_vision",
        fake_process_vision,
    )
    monkeypatch.setattr(
        workflow_registry.TOOL_DEFS["transcribe"],
        "supports_batch",
        False,
    )
    monkeypatch.setattr(Database, "embed", lambda *args, **kwargs: False)
    monkeypatch.setattr(
        "fichero_server.kg.entity_vectors.find_similar",
        lambda *args, **kwargs: [],
    )
    monkeypatch.setattr(
        "fichero_server.kg.entity_vectors.index_entity",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "fichero_server.kg.rebuild.rebuild_kg",
        lambda *args, **kwargs: {
            "entities": 0,
            "claims": 0,
            "triples_written": 0,
        },
    )


def _load_catalogue_workflow_twostage():
    """Catalogue preset with extraction_mode=twostage forced in extract_all config."""
    import copy
    preset = next(p for p in _load_preset_files() if p["name"] == "Catalogue")
    nodes = copy.deepcopy(preset["nodes"])
    for node in nodes:
        if node.get("tool") == "extract_all":
            node.setdefault("config", {})["extraction_mode"] = "twostage"
            break
    return to_workflow_def(
        Workflow(
            id="default-catalogue-twostage-regression-harness",
            name=preset["name"],
            description=preset.get("description", ""),
            nodes=nodes,
            edges=preset["edges"],
            config=preset.get("config", {}),
            folder_path=preset.get("folder_path", "/"),
        )
    )


def _assert_twostage_kg_rows_landed(
    db,
    *,
    catalogue_target_id: str,
    before_entities: int,
    before_claims: int,
) -> None:
    """Assert KG rows were written from the twostage extract_all path.

    Twostage writes claims to page docs when per-page records are present;
    otherwise it falls back to the resolved container document.
    """
    entities = db.all(KnowledgeEntity)
    claims = db.all(KnowledgeClaim)
    assert len(entities) > before_entities, (
        f"no new entities written — twostage kg_payload was empty (got {len(entities)}, "
        f"expected >{before_entities})"
    )
    assert len(claims) > before_claims, (
        f"no new claims written — extract_all did not persist the payload "
        f"(got {len(claims)}, expected >{before_claims})"
    )

    names = {entity.canonical_name for entity in entities}
    assert "Regression Person" in names, f"expected 'Regression Person' in {names}"
    assert "Regression Place" in names, f"expected 'Regression Place' in {names}"

    target_claims = db.query(KnowledgeClaim, source_document_id=catalogue_target_id)
    all_claims = db.all(KnowledgeClaim)
    page_level_claims = [
        claim
        for claim in all_claims
        if claim.source_document_id != catalogue_target_id and claim.entity_ids
    ]
    assert target_claims or page_level_claims, (
        "no twostage claims persisted on container or page docs"
    )
    assert any(claim.entity_ids for claim in all_claims), (
        "claims exist but none have entity_ids linked"
    )


def test_catalogue_twostage_folder_uses_page_records_for_page_scoped_kg(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """Regression for #1403/#1404: page_records-only transcribe output must keep page doc_ids."""
    library_path, selected_doc_id, _catalogue_target_id, child_doc_ids = _seed_folder_with_page_images_fixture(
        tmp_path
    )
    db = db_manager.get_database(library_path)

    async def fake_stage1(**kwargs):
        schema = kwargs.get("schema")
        if schema is not extract_all_module._EntitiesOnly:
            raise AssertionError(f"unexpected schema in stage1 stub: {schema!r}")
        return extract_all_module._EntitiesOnly(
            people=[extract_all_module._EntityOnly(name="Regression Person", entity_type="person")],
            places=[extract_all_module._EntityOnly(name="Regression Place", entity_type="place")],
            organizations=[],
            dates=[],
            events=[],
        )

    async def fake_stage2_claims(*args, **kwargs):
        return [
            {
                "verb": "signed",
                "object": "the fixture ledger",
                "source_text": "Regression Person signed the fixture ledger",
            }
        ]

    async def fake_resumen(*args, **kwargs):
        return ("Catalogue narrative for the regression fixture.", [])

    async def fake_keywords(*args, **kwargs):
        return "regression fixture; workflow harness"

    async def fake_citations_extract(*args, **kwargs):
        return {"text": "", "value": [], "cached": False}

    # Simulate provenance only via state.parallel_results while the direct
    # node output carries plain text. On origin/main, _recover_text_and_records
    # returns early on node text and misses these page_records.
    page_records = [
        {
            "doc_id": doc_id,
            "text": f"Regression Person signed ledger page {index + 1} in Regression Place.",
        }
        for index, doc_id in enumerate(child_doc_ids)
    ]

    async def fake_transcribe(inputs, state, llm_config):
        text = "\n\n".join(record["text"] for record in page_records)
        return {
            "text": text,
            "value": text,
            # Intentionally no "records"/"page_records" on direct output.
            "artifacts": [],
            "output_files": [],
            "error": None,
        }

    monkeypatch.setitem(workflow_registry.TOOLS, "transcribe", fake_transcribe)
    monkeypatch.setattr(
        "fichero_server.workflows.tools.extract_all.chat_structured_with_fallback",
        fake_stage1,
    )
    monkeypatch.setattr(
        "fichero_server.workflows.tools.extract_all._extract_claims_for_entity",
        fake_stage2_claims,
    )
    monkeypatch.setattr("fichero_server.llm.resolve_model_alias", lambda p, m: ("fake", "fake-model"))
    monkeypatch.setattr(Database, "embed", lambda *args, **kwargs: False)
    monkeypatch.setattr(
        "fichero_server.kg.entity_vectors.find_similar",
        lambda *args, **kwargs: [],
    )
    monkeypatch.setattr(
        "fichero_server.kg.entity_vectors.index_entity",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "fichero_server.workflows.tools.catalogue._generate_resumen",
        fake_resumen,
    )
    monkeypatch.setattr(
        "fichero_server.workflows.tools.catalogue._generate_keywords",
        fake_keywords,
    )
    monkeypatch.setattr(
        "fichero_server.workflows.tools.citations_extract.citations_extract",
        fake_citations_extract,
    )
    monkeypatch.setitem(
        workflow_registry.TOOLS,
        "citations_extract",
        fake_citations_extract,
    )
    async def _noop_cleanup(*args, **kwargs):
        return {"text": "", "value": [], "cached": False}
    for _tool in (
        "people_folder_cleanup",
        "places_folder_cleanup",
        "organizations_folder_cleanup",
        "dates_folder_cleanup",
        "events_folder_cleanup",
        "keywords_folder_cleanup",
    ):
        monkeypatch.setitem(workflow_registry.TOOLS, _tool, _noop_cleanup)

    before_claim_rows = db.all(KnowledgeClaim)
    before_claim_ids = {claim.id for claim in before_claim_rows}
    before_claims = len(before_claim_rows)
    before_entities = len(db.all(KnowledgeEntity))

    workflow = _load_catalogue_workflow_twostage()
    state = build_initial_state(
        {"selected_doc_ids": [selected_doc_id]},
        library_path=str(library_path),
    )
    state["parallel_results"] = {
        "shadow_records": [
            {
                "index": index,
                "success": True,
                "result": {"page_records": [record]},
            }
            for index, record in enumerate(page_records)
        ]
    }
    state["workflow_id"] = workflow.id
    state["task_id"] = "test-folder-page-records-catalogue-twostage"

    final_state = asyncio.run(build_graph(workflow, skip_cache=True).ainvoke(state))
    _assert_workflow_completed(final_state)

    claims = db.all(KnowledgeClaim)
    entities = db.all(KnowledgeEntity)
    assert len(entities) > before_entities
    assert len(claims) > before_claims

    page_ids = set(child_doc_ids)
    new_claims = [claim for claim in claims if claim.id not in before_claim_ids]
    stage2_claims = [
        claim
        for claim in new_claims
        if claim.text == "Regression Person signed the fixture ledger."
    ]
    assert stage2_claims, "expected stage-2 fixture claims from extract_all inline-KG path"
    assert all(claim.source_document_id in page_ids for claim in stage2_claims), (
        "stage-2 claims must persist on page/file doc_ids from page_records, "
        "not on the folder container"
    )

def _seed_folder_with_page_images_fixture(
    tmp_path: Path,
) -> tuple[Path, str, str, list[str]]:
    """Seed folder + image leaf docs to emulate folder catalogue on page images."""
    library_path = tmp_path / "folder-page-images.fichero"
    seed(library_path)
    db = db_manager.get_database(library_path)

    folder = Document(
        id="workflow-folder-pages",
        name="Folder page fixture",
        doc_type=DocType.folder,
    )
    db.save(folder)

    child_ids: list[str] = []
    for index in range(2):
        image_path = tmp_path / f"page-{index + 1}.jpg"
        image_path.write_bytes(b"fixture")
        child = Document(
            id=f"workflow-folder-page-{index + 1}",
            parent_id=folder.id,
            name=image_path.name,
            path=str(image_path),
            doc_type=DocType.file,
            file_type=FileType.image,
        )
        db.save(child)
        child_ids.append(child.id)

    return library_path, folder.id, folder.id, child_ids


def test_catalogue_twostage_folder_writes_kg_rows_to_child_docs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """Folder catalogue contract: summary on folder, KG rows on child page/image docs."""
    _install_twostage_stubs(monkeypatch)
    library_path, selected_doc_id, catalogue_target_id, child_doc_ids = _seed_folder_with_page_images_fixture(
        tmp_path
    )
    db = db_manager.get_database(library_path)

    before_claims = len(db.all(KnowledgeClaim))
    before_entities = len(db.all(KnowledgeEntity))

    workflow = _load_catalogue_workflow_twostage()
    state = build_initial_state(
        {"selected_doc_ids": [selected_doc_id]},
        library_path=str(library_path),
    )
    state["workflow_id"] = workflow.id
    state["task_id"] = "test-folder-pages-catalogue-twostage"

    final_state = asyncio.run(build_graph(workflow, skip_cache=True).ainvoke(state))

    _assert_workflow_completed(final_state)
    _assert_twostage_kg_rows_landed(
        db,
        catalogue_target_id=catalogue_target_id,
        before_entities=before_entities,
        before_claims=before_claims,
    )

    folder_claims = [
        claim
        for claim in db.query(KnowledgeClaim, source_document_id=catalogue_target_id)
        if claim.entity_ids
    ]
    child_claims = [
        claim
        for claim in db.all(KnowledgeClaim)
        if claim.source_document_id in set(child_doc_ids) and claim.entity_ids
    ]
    assert child_claims, "expected entity-linked claims on child page/image docs"
    assert not folder_claims, (
        "expected no entity-linked claims on folder container when child "
        "doc_ids are available"
    )
