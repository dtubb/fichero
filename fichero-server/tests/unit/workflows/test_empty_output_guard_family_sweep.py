"""Which workflow families is the #4283 silent-run guard actually able to
protect? (#4283, #4379, #4369)

The NER lane found that ``_detect_empty_text_output`` is structurally
unreachable on the entity surface: it returns "not empty" immediately when
``final_state["files"]`` is falsy — the deliberate no-input-workflow exemption
from #2244/#2245 — and a NER run never carries that key.

That exemption is keyed on ONE state key, and ``files`` is not even a declared
member of the ``State`` TypedDict (``workflows/types.py``): the builder's node
wrapper merges tool results into ``outputs[node_id]`` and returns only
``outputs`` / ``completed_nodes`` / ``output_files`` / ``current_node``. So
whether a family carries top-level ``files`` at all is an accident of how that
family's graph executes, not a property anyone asserted.

This module sweeps one representative shipped preset per family and asks the
only question that matters:

    **If this family's run produces nothing, does the guard say so?**

Method: seed a real library, let the REAL source node resolve it (so ``files``
is genuinely available to whatever wants it), and stub every non-source tool
to return declared-but-empty output — the shape of a run where every model
call refused, every provider was missing, every page failed. Then assert
``_detect_empty_text_output`` reports the run empty.

A family whose test FAILS is a family where a run that produced nothing
reports a green ``completed`` and the user sees "ran but nothing observable
happened" (#4283) with nothing in any activity surface. Those failures are
the deliverable; they are not fixed here and must not be weakened.

The paired no-false-positive sweep matters just as much: a fix that makes the
guard reachable but flags healthy runs turns the signal into noise and the
next genuine silent failure gets ignored.

No test in this module skips. A missing preset, tool, or fixture FAILS
(#4365).
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from tests.integration._seedlib import seed
from tests.unit.workflows.test_default_workflow_e2e_harness import (
    _load_workflow_by_name,
)

from fichero_server.execution.runner import _detect_empty_text_output
from fichero_server.db import db_manager
from fichero_server.models import DocType, Document, FileType
from fichero_server.workflows import registry as workflow_registry
from fichero_server.workflows.builder import build_graph
from fichero_server.workflows.runtime import build_initial_state

import fichero_server.workflows.tools  # noqa: F401

# Source tools resolve the library selection; they are NOT stubbed, so each
# run really does have files to process.
SOURCE_TOOLS = {"files", "collection", "folder", "search"}

# One representative shipped preset per family. Same family, same execution
# shape — covering one member establishes whether the guard can fire for it.
FAMILIES: list[tuple[str, str]] = [
    ("transcribe", "Transcribe"),
    ("transcribe-review", "Transcribe Paleography"),
    ("translate", "Translate"),
    ("catalogue", "Catalogue"),
    ("catalogue-stage", "2 · Extract Entities"),
    ("ner", "NER per-page (local)"),
    ("image-prep", "Prepare Images for OCR"),
    ("image-edit", "Enhance Images"),
    ("split-segment", "Segment Images"),
    ("convert-render", "Convert to Markdown"),
    ("export", "Export to Desktop (MD + DOCX + XLSX)"),
    ("group-merge", "Group Same Documents"),
    ("geo", "Extract Geo"),
    ("table", "Extract Table"),
    ("describe", "Describe (visual)"),
    ("clean-text", "Clean Up Text"),
]

_REAL_TEXT = "Regression Person signed the fixture deed in Regression Place in 1842."


def _seed_mixed_library(tmp_path: Path, name: str) -> tuple[Path, str]:
    """A folder holding one image and one text document.

    Both source shapes resolve, so no family is disadvantaged by the fixture
    rather than by its own behaviour.
    """
    library_path = tmp_path / f"{name}.fichero"
    seed(library_path)
    db = db_manager.get_database(library_path)

    folder = Document(id=f"{name}-folder", name=name, doc_type=DocType.folder)
    db.save(folder)

    image_path = tmp_path / f"{name}-page.jpg"
    image_path.write_bytes(b"\xff\xd8\xff\xe0 fixture jpeg")
    db.save(
        Document(
            id=f"{name}-image",
            parent_id=folder.id,
            name=image_path.name,
            path=str(image_path),
            doc_type=DocType.file,
            file_type=FileType.image,
        )
    )

    text_path = tmp_path / f"{name}-page.txt"
    text_path.write_text(_REAL_TEXT, encoding="utf-8")
    db.save(
        Document(
            id=f"{name}-text",
            parent_id=folder.id,
            name=text_path.name,
            path=str(text_path),
            doc_type=DocType.file,
            file_type=FileType.text,
            page_content=_REAL_TEXT,
            metadata={"transcription": _REAL_TEXT},
        )
    )
    return library_path, folder.id


def _install_stubs(monkeypatch, workflow, *, productive: bool) -> None:
    """Stub every non-source tool.

    ``productive=False`` reproduces the exact #4283 shape: declared output
    ports present but EMPTY, and — critically — no node-level ``error``.

    That "no error" detail is the whole point. A tool that returns
    ``{"error": ...}`` makes the builder raise ``SystemicErrorDetected`` and
    the run aborts loudly; that path already works and is not the bug. #4283
    is the run that finishes clean with nothing to show: "no progress, no
    result, no error". The empty-output guard is the ONLY thing standing
    between that and a green checkmark, which is why its reachability per
    family is worth pinning.

    ``productive=True`` is the healthy run.
    """

    monkeypatch.setattr(
        "fichero_server.llm.resolve_model_alias",
        lambda provider, model: ("fake", "fake-model"),
    )

    def _stub_for(tool_name: str):
        async def _stub(inputs, state, llm_config):
            if productive:
                text = f"{tool_name} output"
                payload: dict = {
                    "text": text,
                    "value": text,
                    "summary": text,
                    "results": [{"file": "/tmp/stub.jpg", "text": text}],
                    "records": [{"doc_id": "stub-doc-1", "text": text}],
                    "page_records": [{"doc_id": "stub-doc-1", "text": text}],
                    "count": 1,
                }
            else:
                payload = {
                    "text": "",
                    "value": "",
                    "summary": "",
                    "artifacts": [],
                    "output_files": [],
                    "records": [],
                    "page_records": [],
                    "documents": [],
                    "files": [],
                    "count": 0,
                    "results": [],
                }
            tool_def = workflow_registry.get_tool_def(tool_name)
            if tool_def:
                for port in tool_def.output_ports:
                    payload.setdefault(port.id, payload["text"])
            return payload

        return _stub

    for node in workflow.nodes:
        if node.tool in SOURCE_TOOLS:
            continue
        monkeypatch.setitem(workflow_registry.TOOLS, node.tool, _stub_for(node.tool))


def _run(preset_name: str, tmp_path: Path, monkeypatch, *, productive: bool) -> dict:
    workflow = _load_workflow_by_name(preset_name)
    library_path, folder_id = _seed_mixed_library(
        tmp_path, f"sweep-{'ok' if productive else 'dead'}"
    )
    _install_stubs(monkeypatch, workflow, productive=productive)

    state = build_initial_state(
        {"selected_doc_ids": [folder_id]}, library_path=str(library_path)
    )
    state["workflow_id"] = workflow.id
    state["task_id"] = f"sweep-{preset_name}"
    return asyncio.run(
        build_graph(
            workflow,
            # Auto-Detect's route_map fan-out is excluded from this sweep
            # (its aggregated output shape needs the dedicated harness in
            # test_builder_route_files_source.py); every other family runs
            # in its real parallel mode so fan-out families genuinely fan out.
            enable_parallel=True,
            skip_cache=True,
        ).ainvoke(state)
    )


@pytest.mark.parametrize(
    ("family", "preset_name"), FAMILIES, ids=[f for f, _ in FAMILIES]
)
def test_guard_fires_when_a_family_run_produces_nothing(
    family: str, preset_name: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """#4283 for every family: a run that produced nothing must say so.

    Failure here means this family is EXEMPT from the silent-run guard: the
    run reports ``completed``, the activity record carries no
    ``empty_output`` metadata and no error, and the user is told nothing.
    """
    final_state = _run(preset_name, tmp_path, monkeypatch, productive=False)

    is_empty, reason = _detect_empty_text_output(final_state)
    assert is_empty, (
        f"family {family!r} (preset {preset_name!r}): every tool returned "
        "empty, errored output and the guard did not fire. "
        f"final_state['files']={final_state.get('files')!r} — the guard "
        "short-circuits on a falsy top-level `files`, so this family's silent "
        "runs are invisible (#4283)."
    )
    assert reason, "an empty run must carry a machine-readable reason"


@pytest.mark.parametrize(
    ("family", "preset_name"), FAMILIES, ids=[f for f, _ in FAMILIES]
)
def test_guard_stays_quiet_when_a_family_run_produces_output(
    family: str, preset_name: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """The other half of the contract: no false positives.

    Making the guard reachable is only half a fix. If it then flags healthy
    runs, every run looks broken, the warning is ignored, and the next
    genuine silent failure passes unnoticed — the same outcome #4283 was
    filed for.
    """
    final_state = _run(preset_name, tmp_path, monkeypatch, productive=True)

    is_empty, reason = _detect_empty_text_output(final_state)
    assert not is_empty, (
        f"family {family!r} (preset {preset_name!r}): a run where every tool "
        f"returned real output was flagged as empty ({reason!r})"
    )


def test_completed_run_state_carries_the_top_level_stats_the_runner_reads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """The single root cause behind the whole failing sweep, stated once.

    KNOWN FAILING against the current code (reported, not weakened).

    ``_run_workflow_in_background`` builds its completion metadata by reading
    TOP-LEVEL keys off the final state — ``final_state["files"]`` for
    ``total_files``, ``["artifacts"]`` for ``total_artifacts``,
    ``["results"]`` for ``total_results`` — and then hands the same state to
    ``_detect_empty_text_output``, which gates on ``files``.

    The builder's node wrapper never writes any of them. It merges each
    tool's result into ``outputs[node_id]`` and returns only ``outputs``,
    ``completed_nodes``, ``current_node`` and ``output_files``; ``files`` is
    not even a member of the ``State`` TypedDict. The one place a top-level
    ``files`` is constructed is the per-file parallel Send branch state,
    which does not survive into the merged final state.

    Two consequences, both user-visible:
      * every run's completion metadata reports ``nodes_completed`` and
        nothing else — no file, artifact or result counts in any activity
        surface;
      * the #4283 silent-run guard can never fire on any shipped preset, so
        the fix that closed #4283 is inert at runtime. The existing unit
        tests for it pass because they hand it a hand-built state carrying
        ``files`` — a state shape the runtime does not produce.

    This test asserts the contract the runner already assumes: a run that
    processed files says so in its final state.
    """
    final_state = _run("Transcribe", tmp_path, monkeypatch, productive=True)

    assert final_state.get("completed_nodes"), "precondition: the run must have run"
    assert final_state.get("files"), (
        "a completed run that processed files carries no top-level `files` in "
        f"its final state (keys: {sorted(final_state)}) — every stat the "
        "runner reports and the #4283 empty-output guard both read that key"
    )


@pytest.mark.parametrize(
    ("family", "preset_name"), FAMILIES, ids=[f for f, _ in FAMILIES]
)
def test_terminal_finalization_can_find_each_family_documents(
    family: str, preset_name: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """#4315 for every family: a dying run must be able to release its docs.

    ``finalize_run_documents`` only settles the ids
    ``collect_processed_document_ids`` recovers from the terminal state, and
    that helper reads ``outputs[node_id]["documents"]`` plus a couple of
    top-level fallbacks. A family whose graph does not leave its documents
    there gets an empty set — finalization becomes a silent no-op and every
    document an upstream content tool marked ``processing`` keeps a permanent
    spinner that no later run repairs.

    Run productively here on purpose: recovery must not depend on the run
    having succeeded, and a family that cannot be recovered even on the happy
    path certainly cannot be recovered when it dies.
    """
    from fichero_server.workflows.completion import collect_processed_document_ids

    final_state = _run(preset_name, tmp_path, monkeypatch, productive=True)

    recovered = collect_processed_document_ids(final_state)
    assert recovered, (
        f"family {family!r} (preset {preset_name!r}): no document ids "
        "recoverable from the terminal state — finalize_run_documents would "
        "be a no-op and every touched document would stay at "
        "Status.processing forever (#4315)"
    )
