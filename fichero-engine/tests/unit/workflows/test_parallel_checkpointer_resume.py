"""Checkpointer-backed regression tests for the workflow PARALLEL run path (#2532).

These are DIAGNOSTICS for the graph-level Send fan-out that is currently
HARD-DISABLED on the live run path (runner.py sets enable_parallel=False because
of #1665). They build a minimal real graph

    SOURCE (files) ──fan-out──▶ PARALLEL (transcribe) ──aggregate──▶ DOWNSTREAM

with ``enable_parallel=True``, attach a REAL ``AsyncDuckDBCheckpointer``, and
drive it through the SAME streaming entry point the runner uses
(``app.astream_events(..., version="v2")``) — not ``ainvoke``.

What each test asserts:

* ``test_downstream_node_executes_after_parallel_aggregate`` — #1665 repro: after
  the aggregate node completes, the DOWNSTREAM node must actually run and produce
  output. If the fan-out checkpoints a completed aggregate but fails to schedule
  the downstream node, THIS test FAILS — that is the expected, useful signal that
  #1665 is still live.

* ``test_per_page_fanout_distinct_artifacts_no_parent_reroute`` — a SOURCE emitting
  N pages of ONE document must fan out to N DISTINCT parallel branches, each
  carrying its own page-child document (never the parent), producing N distinct
  artifacts with distinct per-page cache keys (the #896 shared-key-bleed contract).

* ``test_resume_from_mid_fanout_completes_each_branch_once`` — interrupting before
  the parallel process node leaves a mid-fan-out checkpoint; resuming on the same
  ``thread_id`` must complete every remaining branch EXACTLY once (no double
  processing, no missing branch) and then run downstream once.

No real LLM/vision/provider is called — fake tools are injected into the registry.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import pytest

from fichero.workflows import registry
from fichero.workflows.builder import build_graph
from fichero.workflows.cache import compute_cache_key
from fichero.workflows.checkpointer import AsyncDuckDBCheckpointer
from fichero.workflows.types import EdgeDef, NodeDef, WorkflowDef


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def temp_db():
    """Temporary DuckDB path for a real checkpointer (mirrors test_checkpointer)."""
    temp_dir = tempfile.mkdtemp()
    db_path = Path(temp_dir) / "checkpoint.duckdb"
    yield db_path
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def page_paths(tmp_path):
    """One real on-disk file shared by all 'pages' (the per-page-PDF scenario).

    All page children share the parent PDF's path; only the Document.id differs.
    A real file keeps compute_cache_key's file-identity stable.
    """
    pdf = tmp_path / "scan.pdf"
    pdf.write_bytes(b"%PDF-1.4 stub bytes")
    return str(pdf)


def _install_fake_tools(monkeypatch, source_files, source_documents, transcribe_calls):
    """Inject fake source / parallel / downstream tools into the registry.

    - ``files``  (SOURCE_TOOL): returns the provided files + per-page documents.
    - ``transcribe`` (PARALLEL_TOOL): records each per-branch invocation and
      returns a per-page artifact tagged with the page-child doc id.
    - ``fake_sink`` (standard downstream): records that it ran.

    Returns a dict with recorders the tests assert on.
    """
    downstream_runs: list[dict] = []

    async def fake_files(*, inputs=None, state=None, llm_config=None, **_kw):
        # SOURCE_TOOL contract: expose files + documents for fan-out.
        return {"files": list(source_files), "documents": list(source_documents)}

    async def fake_transcribe(*, inputs=None, state=None, llm_config=None, **_kw):
        inputs = inputs or {}
        files = inputs.get("files") or []
        docs = inputs.get("documents") or []
        file_path = files[0] if files else ""
        doc = docs[0] if docs else None
        doc_id = doc.get("id") if isinstance(doc, dict) else None
        transcribe_calls.append({"file": file_path, "doc_id": doc_id})
        text = f"transcribed::{doc_id}"
        return {
            "text": text,
            # Per-page artifact: must be attributed to the page child, never
            # rerouted onto the parent PDF.
            "artifacts": [{"document_id": doc_id, "file": file_path, "text": text}],
        }

    async def fake_sink(*, inputs=None, state=None, llm_config=None, **_kw):
        inputs = inputs or {}
        downstream_runs.append({"inputs": dict(inputs)})
        return {"downstream_ran": True, "received_text": inputs.get("text")}

    async def fake_enhance(*, inputs=None, state=None, llm_config=None, **_kw):
        # A standard (non-parallel) sibling of the parallel branch.
        return {"enhanced": True, "files": list(source_files)}

    monkeypatch.setitem(registry.TOOLS, "files", fake_files)
    monkeypatch.setitem(registry.TOOLS, "transcribe", fake_transcribe)
    monkeypatch.setitem(registry.TOOLS, "fake_sink", fake_sink)
    monkeypatch.setitem(registry.TOOLS, "fake_enhance", fake_enhance)

    return {"downstream_runs": downstream_runs}


def _build_workflow() -> WorkflowDef:
    """SOURCE → transcribe (parallel) → downstream sink."""
    return WorkflowDef(
        id="wf-parallel-regression",
        name="Parallel Checkpointer Regression",
        provider="openai",
        model="gpt-4o",
        nodes=[
            NodeDef(id="src", tool="files", label="Source", config={}),
            NodeDef(
                id="tx",
                tool="transcribe",
                label="Transcribe",
                # Disable the quality gate so the fake's clean text is never
                # second-guessed; keeps the run deterministic.
                config={"quality_gate": False},
            ),
            NodeDef(
                id="down",
                tool="fake_sink",
                label="Downstream",
                config={"quality_gate": False},
            ),
        ],
        edges=[
            EdgeDef(source="src", target="tx", source_port="files", target_port="files"),
            EdgeDef(source="tx", target="down", source_port="text", target_port="text"),
        ],
    )


def _build_fanin_workflow() -> WorkflowDef:
    """Fan-in topology closer to the Catalogue failure (#1665).

        SOURCE ──▶ transcribe (parallel) ──aggregate──┐
        SOURCE ──▶ enhance (standard) ────────────────┴──▶ DOWNSTREAM

    DOWNSTREAM has TWO incoming edges — one from a parallel ``_aggregate``
    source, one from a standard node — so it is wired via the multi-source
    waiting edge (``graph.add_edge([..., 'Transcribe_aggregate'], 'Downstream')``).
    """
    return WorkflowDef(
        id="wf-parallel-fanin",
        name="Parallel Fan-in Regression",
        provider="openai",
        model="gpt-4o",
        nodes=[
            NodeDef(id="src", tool="files", label="Source", config={}),
            NodeDef(id="tx", tool="transcribe", label="Transcribe", config={"quality_gate": False}),
            NodeDef(id="enh", tool="fake_enhance", label="Enhance", config={"quality_gate": False}),
            NodeDef(id="down", tool="fake_sink", label="Downstream", config={"quality_gate": False}),
        ],
        edges=[
            EdgeDef(source="src", target="tx", source_port="files", target_port="files"),
            EdgeDef(source="src", target="enh", source_port="files", target_port="files"),
            EdgeDef(source="tx", target="down", source_port="text", target_port="text"),
            EdgeDef(source="enh", target="down", source_port="files", target_port="files"),
        ],
    )


def _three_pages(page_paths):
    """Three page-children of ONE parent PDF; shared path, distinct ids."""
    files = [page_paths, page_paths, page_paths]
    documents = [
        {"id": "page-1", "path": page_paths, "parent_id": "parent-pdf", "sequence": 1},
        {"id": "page-2", "path": page_paths, "parent_id": "parent-pdf", "sequence": 2},
        {"id": "page-3", "path": page_paths, "parent_id": "parent-pdf", "sequence": 3},
    ]
    return files, documents


async def _drive(app, initial_state, config):
    """Consume astream_events exactly as runner.py does (streaming, not ainvoke)."""
    async for _event in app.astream_events(initial_state, config=config, version="v2"):
        pass


# ---------------------------------------------------------------------------
# 1. #1665 — downstream scheduling after parallel aggregate
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_downstream_node_executes_after_parallel_aggregate(
    temp_db, page_paths, monkeypatch
):
    """#1665: after transcribe fan-out aggregates, DOWNSTREAM must run + emit output.

    Drives the real Send fan-out through astream_events with a real
    AsyncDuckDBCheckpointer attached. FAILS if the aggregate is checkpointed but
    the downstream node is never scheduled (branch:to:Downstream = None) — the
    bug that forced enable_parallel=False on the live runner.
    """
    files, documents = _three_pages(page_paths)
    transcribe_calls: list[dict] = []
    rec = _install_fake_tools(monkeypatch, files, documents, transcribe_calls)

    checkpointer = AsyncDuckDBCheckpointer.from_db_path(temp_db)
    app = build_graph(
        _build_workflow(),
        enable_parallel=True,
        checkpointer=checkpointer,
        skip_cache=True,
    )

    config = {"configurable": {"thread_id": "t-1665", "checkpoint_ns": ""}}
    initial_state = {
        "workflow_id": "wf-parallel-regression",
        "library_path": "",
        "inputs": {},
        "selected_doc_ids": [],
    }

    await _drive(app, initial_state, config)

    # All three branches ran.
    assert len(transcribe_calls) == 3, (
        f"expected 3 fan-out branches, got {len(transcribe_calls)}"
    )

    snapshot = await app.aget_state(config)
    values = snapshot.values
    outputs = values.get("outputs", {})
    completed = values.get("completed_nodes", [])

    # The crux of #1665: the downstream node must have executed.
    assert "down" in outputs, (
        "#1665 STILL LIVE: aggregate completed but downstream node was never "
        f"scheduled. outputs keys={sorted(outputs)}, completed_nodes={completed}, "
        f"next={getattr(snapshot, 'next', None)}"
    )
    assert outputs["down"].get("downstream_ran") is True
    assert "down" in completed
    assert len(rec["downstream_runs"]) == 1, (
        f"downstream must run exactly once, ran {len(rec['downstream_runs'])}x"
    )


@pytest.mark.asyncio
async def test_downstream_with_parallel_aggregate_fanin_is_scheduled(
    temp_db, page_paths, monkeypatch
):
    """#1665 (fan-in variant): downstream fed by a parallel aggregate + a sibling.

    This mirrors the Catalogue topology more closely: the downstream node waits
    on BOTH the transcribe ``_aggregate`` and a standard ``enhance`` node via the
    multi-source waiting edge. FAILS if the Send fan-out checkpoints the aggregate
    but the fan-in never releases the downstream node.
    """
    files, documents = _three_pages(page_paths)
    transcribe_calls: list[dict] = []
    rec = _install_fake_tools(monkeypatch, files, documents, transcribe_calls)

    checkpointer = AsyncDuckDBCheckpointer.from_db_path(temp_db)
    app = build_graph(
        _build_fanin_workflow(),
        enable_parallel=True,
        checkpointer=checkpointer,
        skip_cache=True,
    )

    config = {"configurable": {"thread_id": "t-1665-fanin", "checkpoint_ns": ""}}
    initial_state = {
        "workflow_id": "wf-parallel-fanin",
        "library_path": "",
        "inputs": {},
        "selected_doc_ids": [],
    }

    await _drive(app, initial_state, config)

    assert len(transcribe_calls) == 3
    snapshot = await app.aget_state(config)
    outputs = snapshot.values.get("outputs", {})
    completed = snapshot.values.get("completed_nodes", [])

    assert "enh" in outputs, "sibling standard node must run"
    assert "down" in outputs, (
        "#1665 STILL LIVE (fan-in): aggregate + sibling completed but downstream "
        f"never scheduled. outputs keys={sorted(outputs)}, completed={completed}, "
        f"next={getattr(snapshot, 'next', None)}"
    )
    assert outputs["down"].get("downstream_ran") is True
    assert len(rec["downstream_runs"]) == 1


# ---------------------------------------------------------------------------
# 2. Per-page save contract under parallel (no parent reroute, distinct keys)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_per_page_fanout_distinct_artifacts_no_parent_reroute(
    temp_db, page_paths, monkeypatch
):
    """N pages of one document → N distinct artifacts, none rerouted to the parent.

    Asserts the fan-out delivered a DISTINCT page-child document to each branch
    (the per-page save contract) and that per-page cache keys are distinct even
    though all pages share the parent PDF's path (#896 shared-key-bleed guard).
    """
    files, documents = _three_pages(page_paths)
    transcribe_calls: list[dict] = []
    _install_fake_tools(monkeypatch, files, documents, transcribe_calls)

    checkpointer = AsyncDuckDBCheckpointer.from_db_path(temp_db)
    app = build_graph(
        _build_workflow(),
        enable_parallel=True,
        checkpointer=checkpointer,
        skip_cache=True,
    )

    config = {"configurable": {"thread_id": "t-perpage", "checkpoint_ns": ""}}
    initial_state = {
        "workflow_id": "wf-parallel-regression",
        "library_path": "",
        "inputs": {},
        "selected_doc_ids": [],
    }

    await _drive(app, initial_state, config)

    # One branch per page, each carrying its own page-child id.
    assert len(transcribe_calls) == 3
    delivered_ids = [c["doc_id"] for c in transcribe_calls]
    assert set(delivered_ids) == {"page-1", "page-2", "page-3"}, (
        f"each branch must get a distinct page child; got {delivered_ids}"
    )
    assert "parent-pdf" not in delivered_ids, (
        "per-page save must NOT reroute a branch onto the parent PDF"
    )

    # Aggregated artifacts: one per page, distinct doc ids, none the parent.
    snapshot = await app.aget_state(config)
    artifacts = snapshot.values.get("outputs", {}).get("tx", {}).get("artifacts", [])
    artifact_ids = [a.get("document_id") for a in artifacts]
    assert len(artifacts) == 3, f"expected 3 per-page artifacts, got {artifact_ids}"
    assert set(artifact_ids) == {"page-1", "page-2", "page-3"}
    assert "parent-pdf" not in artifact_ids

    # #896: distinct Document.id must yield distinct cache keys despite the
    # shared parent-PDF path (otherwise page-1's result bleeds onto pages 2-3).
    keys = {
        compute_cache_key(
            workflow_id="wf-parallel-regression",
            node_id="tx",
            tool="transcribe",
            config={},
            provider="openai",
            model="gpt-4o",
            file_path=page_paths,
            document_id=doc["id"],
        )
        for doc in documents
    }
    assert len(keys) == 3, (
        "#896: page children sharing one path must NOT share a cache key"
    )


# ---------------------------------------------------------------------------
# 3. Resume from a mid-fan-out checkpoint — each branch exactly once
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_resume_from_mid_fanout_completes_each_branch_once(
    temp_db, page_paths, monkeypatch
):
    """Interrupt before the parallel node, then resume on the same thread_id.

    The first run computes the source fan-out and checkpoints BEFORE any branch
    executes (interrupt_before the process node). Resuming must run every branch
    EXACTLY once, aggregate, and run downstream once — no double processing, no
    missing branch.
    """
    files, documents = _three_pages(page_paths)
    transcribe_calls: list[dict] = []
    rec = _install_fake_tools(monkeypatch, files, documents, transcribe_calls)

    # Single shared checkpointer across both app instances = durable resume.
    checkpointer = AsyncDuckDBCheckpointer.from_db_path(temp_db)
    workflow = _build_workflow()

    config = {"configurable": {"thread_id": "t-resume", "checkpoint_ns": ""}}
    initial_state = {
        "workflow_id": "wf-parallel-regression",
        "library_path": "",
        "inputs": {},
        "selected_doc_ids": [],
    }

    # Run 1: stop before the parallel process node fires (mid-fan-out checkpoint).
    app1 = build_graph(
        workflow,
        enable_parallel=True,
        checkpointer=checkpointer,
        interrupt_before=["Transcribe_process"],
        skip_cache=True,
    )
    await _drive(app1, initial_state, config)

    assert len(transcribe_calls) == 0, (
        "no branch should have run yet — interrupt fired before the process node; "
        f"ran {len(transcribe_calls)}"
    )
    mid = await app1.aget_state(config)
    assert "down" not in mid.values.get("outputs", {}), (
        "downstream must not have run at the mid-fan-out checkpoint"
    )

    # Run 2 (simulated restart): fresh app, same checkpointer + thread, resume.
    app2 = build_graph(
        workflow,
        enable_parallel=True,
        checkpointer=checkpointer,
        skip_cache=True,
    )
    await _drive(app2, None, config)

    # Every branch ran EXACTLY once across both runs (no double-processing).
    assert len(transcribe_calls) == 3, (
        f"resume must complete each branch exactly once, got {len(transcribe_calls)} "
        f"calls: {[c['doc_id'] for c in transcribe_calls]}"
    )
    assert sorted(c["doc_id"] for c in transcribe_calls) == ["page-1", "page-2", "page-3"]

    final = await app2.aget_state(config)
    outputs = final.values.get("outputs", {})
    assert "down" in outputs and outputs["down"].get("downstream_ran") is True, (
        "downstream must run after resume completes the fan-out + aggregate"
    )
    assert len(rec["downstream_runs"]) == 1, (
        f"downstream must run exactly once, ran {len(rec['downstream_runs'])}x"
    )
