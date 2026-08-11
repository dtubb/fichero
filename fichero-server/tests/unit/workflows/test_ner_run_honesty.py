"""A named-entity-extraction run must tell the truth about what it did
(#4379, #4283, #4315).

Three honest-failure contracts, all NER-specific:

1. **A run where every extraction call failed must not read as success.**
   #4283 is the canonical version of this: the run went green, no artifacts,
   no error anywhere, "ran but nothing observable happened".
2. **A run that succeeded must not read as failure.** The inverse matters
   just as much: if the empty-output detector flags a NER run that really did
   create entities, the #4283 signal becomes noise and the next genuine
   silent failure is ignored.
3. **A terminal NER run must release its documents.** #4315's finalization
   boundary is only as good as ``collect_processed_document_ids`` finding
   the NER run's documents in its terminal state — if that returns an empty
   set, ``finalize_run_documents`` is a no-op and every touched document
   spins forever, which is what a dropped connection mid-NER (#4379) looks
   like from the library.

Nothing here skips. A missing model / fixture makes these FAIL (#4365).
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from tests.integration._seedlib import seed
from tests.unit.workflows.test_default_workflow_e2e_harness import (
    FIXTURE_TEXT,
    _load_workflow_by_name,
)

from fichero_server.db import Database, db_manager
from fichero_server.execution.runner import _detect_empty_text_output
from fichero_server.models import DocType, Document, FileType, Status
from fichero_server.models.knowledge import KnowledgeEntity
from fichero_server.workflows.builder import build_graph
from fichero_server.workflows.completion import (
    collect_processed_document_ids,
    finalize_run_documents,
)
from fichero_server.workflows.runtime import build_initial_state

import fichero_server.workflows.tools  # noqa: F401
import fichero_server.workflows.tools.extract_all as extract_all_module

STAGE_2_PRESET = "2 · Extract Entities"


class ModelUnavailable(RuntimeError):
    """Stand-in for the real failure mode: no model, no key, open breaker."""


def _seed_corpus(tmp_path: Path, name: str, *, text: str | None, pages: int = 2):
    library_path = tmp_path / f"{name}.fichero"
    seed(library_path)
    db = db_manager.get_database(library_path)

    folder = Document(id=f"{name}-folder", name=name, doc_type=DocType.folder)
    db.save(folder)
    doc_ids: list[str] = []
    for index in range(pages):
        source_file = tmp_path / f"{name}-{index + 1}.txt"
        source_file.write_text(text or "", encoding="utf-8")
        doc = Document(
            id=f"{name}-doc-{index + 1}",
            parent_id=folder.id,
            name=source_file.name,
            path=str(source_file),
            doc_type=DocType.file,
            file_type=FileType.text,
            page_content=text,
            metadata={"transcription": text} if text else {},
        )
        db.save(doc)
        doc_ids.append(doc.id)
    return library_path, folder.id, doc_ids


def _stub_entity_model(monkeypatch, impl) -> None:
    monkeypatch.setattr(
        "fichero_server.llm.resolve_model_alias",
        lambda provider, model: ("fake", "fake-model"),
    )
    monkeypatch.setattr(
        "fichero_server.workflows.tools.extract_entities_only."
        "chat_structured_with_fallback",
        impl,
    )
    monkeypatch.setattr(Database, "embed", lambda *args, **kwargs: False)
    monkeypatch.setattr(
        "fichero_server.knowledge.entity_vectors.find_similar", lambda *a, **k: []
    )
    monkeypatch.setattr(
        "fichero_server.knowledge.entity_vectors.index_entity", lambda *a, **k: None
    )


async def _two_entities(**kwargs):
    if kwargs.get("schema") is not extract_all_module._EntitiesOnly:
        raise AssertionError(f"unexpected schema: {kwargs.get('schema')!r}")
    return extract_all_module._EntitiesOnly(
        people=[
            extract_all_module._EntityOnly(
                name="Regression Person", entity_type="person"
            )
        ],
        places=[
            extract_all_module._EntityOnly(name="Regression Place", entity_type="place")
        ],
        organizations=[],
        dates=[],
        events=[],
    )


def _initial_state(library_path: Path, selected_doc_id: str, task_id: str, workflow):
    state = build_initial_state(
        {"selected_doc_ids": [selected_doc_id]},
        library_path=str(library_path),
    )
    state["workflow_id"] = workflow.id
    state["task_id"] = task_id
    return state


def _run_stage_2(library_path: Path, selected_doc_id: str, task_id: str):
    workflow = _load_workflow_by_name(STAGE_2_PRESET)
    state = _initial_state(library_path, selected_doc_id, task_id, workflow)
    return workflow, asyncio.run(build_graph(workflow, skip_cache=True).ainvoke(state))


def _run_stage_2_checkpointed(library_path: Path, selected_doc_id: str, task_id: str):
    """Run through the checkpointed path the live runner uses.

    The runner never sees a returned final state on failure — the node raises,
    it catches, and its terminal finalizer reads the LAST CHECKPOINT to find
    the run's documents. Reproduce that exactly, so this test pins the state
    the finalizer actually gets rather than a convenient in-memory one.
    """
    from fichero_server.workflows.runtime import create_compiled_app

    workflow = _load_workflow_by_name(STAGE_2_PRESET)
    db = db_manager.get_database(library_path)
    app, checkpointer = create_compiled_app(
        workflow, db_path=db.path, enable_parallel=False, skip_cache=True
    )
    state = _initial_state(library_path, selected_doc_id, task_id, workflow)
    config = {"configurable": {"thread_id": task_id}}

    async def run():
        raised: Exception | None = None
        try:
            await app.ainvoke(state, config=config)
        except Exception as exc:
            raised = exc
        tup = await checkpointer.aget_tuple(config)
        terminal = (tup.checkpoint.get("channel_values") or {}) if tup else {}
        return raised, terminal

    return workflow, asyncio.run(run())


class TestFailedExtractionIsNotSuccess:
    def test_model_unavailable_surfaces_as_a_run_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """Every extraction call failing must not complete cleanly (#4283)."""

        async def always_fails(**_kwargs):
            raise ModelUnavailable("no entity-capable model configured")

        _stub_entity_model(monkeypatch, always_fails)
        library_path, folder_id, _ = _seed_corpus(
            tmp_path, "ner-fail", text=FIXTURE_TEXT
        )
        db = db_manager.get_database(library_path)
        before_entities = len(db.all(KnowledgeEntity))

        from fichero_server.workflows.builder import SystemicErrorDetected

        with pytest.raises(SystemicErrorDetected):
            _run_stage_2(library_path, folder_id, "ner-fail-run-1")

        assert len(db.all(KnowledgeEntity)) == before_entities, (
            "a failed extraction must not invent entity rows"
        )

    def test_documents_without_text_report_zero_processed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """No text is a real outcome, and must be reported as zero — not as
        a successful extraction of nothing."""
        calls: list[str] = []

        async def record_call(**kwargs):
            calls.append(str(kwargs.get("prompt")))
            return await _two_entities(**kwargs)

        _stub_entity_model(monkeypatch, record_call)
        library_path, folder_id, _ = _seed_corpus(tmp_path, "ner-empty", text=None)
        db = db_manager.get_database(library_path)
        before_entities = len(db.all(KnowledgeEntity))

        workflow, final_state = _run_stage_2(
            library_path, folder_id, "ner-empty-run-1"
        )
        node_id = next(
            node.id for node in workflow.nodes if node.tool == "extract_entities_only"
        )
        summary = ((final_state.get("outputs") or {}).get(node_id) or {}).get(
            "summary"
        ) or {}

        assert calls == [], (
            "extraction called the model on documents with no text — "
            f"prompts: {calls!r}"
        )
        assert summary.get("documents_processed") == 0, (
            f"no-text documents reported as processed: {summary}"
        )
        assert summary.get("entities_created", 0) == 0
        assert len(db.all(KnowledgeEntity)) == before_entities


class TestNerRunVisibilityToEmptyOutputDetector:
    def test_ner_run_is_visible_to_the_empty_output_detector(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """#4283's silent-run detector must actually cover the NER surface.

        KNOWN FAILING against the current code (reported, not weakened).

        ``_detect_empty_text_output`` is the guard that turned "ran but
        nothing observable happened" into a visible failure. It short-circuits
        to *not empty* the moment ``final_state["files"]`` is falsy — the
        deliberate no-input-workflow exemption from #2244/#2245.

        A NER run over real documents carries its selection as ``documents``,
        never as ``files``. So the guard exits before it looks at anything:
        a NER run that extracts NOTHING — no model, refused prompts, every
        chunk failed — cannot be flagged, and reports a green ``completed``.
        #4283 is fixed for the vision/transcription surface and open for the
        entity surface.

        This test pins BOTH directions, because a fix that only makes the
        detector reachable would then wrongly flag every *successful* NER run
        (entity output is ``{"summary", "count"}`` — no text, no artifacts, no
        results rows), turning the signal into noise. Whatever lane-4379 does
        must satisfy both halves.
        """
        _stub_entity_model(monkeypatch, _two_entities)
        library_path, folder_id, doc_ids = _seed_corpus(
            tmp_path, "ner-ok", text=FIXTURE_TEXT
        )
        db = db_manager.get_database(library_path)

        _workflow, final_state = _run_stage_2(library_path, folder_id, "ner-ok-run-1")

        # Preconditions: the run really did succeed and really did land rows.
        assert not final_state.get("error"), final_state.get("error")
        created = {
            entity.canonical_name for entity in db.all(KnowledgeEntity)
        }
        assert {"Regression Person", "Regression Place"} <= created, created
        # ...and the detector is actually reachable for this run. It short-
        # circuits to "not empty" when state carries no `files`, which would
        # make this assertion vacuous — and would separately mean a NER run
        # that produced NOTHING could never be flagged either (#4283).
        assert final_state.get("files"), (
            "a NER run over real documents carries no `files` in its state, so "
            "the empty-output detector can never fire on it in either "
            "direction — a NER run that produces nothing stays invisible (#4283)"
        )

        is_empty, reason = _detect_empty_text_output(final_state)
        assert not is_empty, (
            "a NER run that created entity rows was flagged as producing no "
            f"output ({reason!r}) — the empty-output detector does not "
            "understand entity-shaped output (#4283)"
        )


class TestTerminalPathReleasesDocuments:
    def test_failed_ner_run_state_lets_finalization_find_its_documents(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """#4315 + #4379: after a NER run dies, no document stays spinning.

        The finalization boundary can only release what
        ``collect_processed_document_ids`` recovers from the terminal state.
        If a NER run's state does not carry its documents, every document an
        upstream content tool left at ``Status.processing`` keeps a permanent
        spinner and no later run repairs it.
        """

        async def always_fails(**_kwargs):
            raise ModelUnavailable("connection lost mid-extraction")

        _stub_entity_model(monkeypatch, always_fails)
        library_path, folder_id, doc_ids = _seed_corpus(
            tmp_path, "ner-terminal", text=FIXTURE_TEXT
        )
        db = db_manager.get_database(library_path)

        # An upstream content tool (transcription / LLM content) marks every
        # document it touches as processing; the run boundary owns the flip.
        for doc_id in doc_ids:
            doc = db.get(Document, doc_id)
            doc.status = Status.processing
            db.save(doc)

        _workflow, (raised, terminal_state) = _run_stage_2_checkpointed(
            library_path, folder_id, "ner-terminal-run-1"
        )
        assert raised is not None, "precondition: the run must have failed"

        recovered = collect_processed_document_ids(terminal_state)
        assert set(doc_ids) <= recovered, (
            "the failed NER run's terminal state does not name its documents "
            f"(recovered {sorted(recovered)}, expected {sorted(doc_ids)}) — "
            "finalize_run_documents would be a no-op and every document would "
            "stay at Status.processing forever (#4315)"
        )

        finalize_run_documents(
            db,
            recovered,
            "failed",
            workflow_run={
                "thread_id": "ner-terminal-run-1",
                "workflow_id": "wf-ner-stage2",
                "result": {"status": "failed"},
            },
        )
        for doc_id in doc_ids:
            after = db.get(Document, doc_id)
            assert after.status != Status.processing, (
                f"{doc_id} still spinning after a failed NER run (#4315)"
            )
            assert after.workflow_runs, (
                f"{doc_id} has no provenance entry for the failed run"
            )
