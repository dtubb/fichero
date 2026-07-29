"""Regression tests for the parallel run-path FLIP (#2532/#2541 C3).

The capstone change turned graph-level parallel fan-out ON for the live run
path: ``runner.py`` now builds ``create_compiled_app(..., enable_parallel=True)``
where it previously hard-coded ``False`` (the #1665 deferral). These tests lock
the three things that flip must not silently reopen:

1. **The flip took effect** — the runner's build entry point
   (``create_compiled_app``) yields a graph with the per-file fan-out topology
   (``*_process`` + ``*_aggregate`` nodes), and ``runner.py`` itself passes
   ``enable_parallel=True`` (source guard, so a future edit back to ``False`` is
   caught).

2. **Bounded scheduling** — a large file list does NOT run all branches at once.
   The module-global vision semaphore (cap ``VISION_FAN_OUT_CONCURRENCY``) caps
   the number of simultaneously in-flight parallel tool bodies regardless of how
   many files fan out, so peak heavy memory is O(cap), not O(files). Also locks
   the Send-payload trim (#2532): each Send carries NO ``outputs`` blob.

3. **preview == run topology** — the graph the runner builds for execution
   (now parallel) has the SAME topology as the preview/diagram graph (also
   parallel). This is what stops "the diagram lies": both paths build with
   ``enable_parallel=True`` now, so the rendered Mermaid matches what runs.

No real LLM/vision/provider is called — fake tools are injected into the
registry, mirroring test_parallel_checkpointer_resume.py.
"""

from __future__ import annotations

import asyncio
import inspect
import shutil
import tempfile
from pathlib import Path

import pytest

from fichero_server.execution import runner
from fichero_server.workflows import registry
from fichero_server.workflows.builder import (
    VISION_FAN_OUT_CONCURRENCY,
    _make_fan_out_function,
    build_graph,
)
from fichero_server.workflows.checkpointer import AsyncDuckDBCheckpointer
from fichero_server.workflows.runtime import create_compiled_app
from fichero_server.workflows.types import EdgeDef, NodeDef, WorkflowDef, _merge_outputs


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def temp_db():
    temp_dir = tempfile.mkdtemp()
    db_path = Path(temp_dir) / "checkpoint.duckdb"
    yield db_path
    shutil.rmtree(temp_dir, ignore_errors=True)


def _parallel_workflow() -> WorkflowDef:
    """SOURCE (files) → transcribe (parallel) → downstream sink.

    The downstream node uses the real, registered ``aggregate`` tool (neither a
    SOURCE nor a PARALLEL tool) so the topology tests can build the graph
    WITHOUT monkeypatching the registry. Tests that actually execute the graph
    override these tools with fakes via monkeypatch.
    """
    return WorkflowDef(
        id="wf-flip",
        name="Flip Regression",
        provider="openai",
        model="gpt-4o",
        nodes=[
            NodeDef(id="src", tool="files", label="Source", config={}),
            NodeDef(id="tx", tool="transcribe", label="Transcribe",
                    config={"quality_gate": False}),
            NodeDef(id="down", tool="aggregate", label="Downstream",
                    config={"quality_gate": False}),
        ],
        edges=[
            EdgeDef(source="src", target="tx", source_port="files", target_port="files"),
            EdgeDef(source="tx", target="down", source_port="text", target_port="text"),
        ],
    )


def _graph_topology(app) -> tuple[set[str], set[tuple[str, str]]]:
    """Extract (node-name set, edge (source,target) set) from a compiled app."""
    g = app.get_graph()
    nodes = set(g.nodes.keys())
    edges = {(e.source, e.target) for e in g.edges}
    return nodes, edges


async def _drive(app, initial_state, config):
    async for _ in app.astream_events(initial_state, config=config, version="v2"):
        pass


# ---------------------------------------------------------------------------
# 1. The flip took effect
# ---------------------------------------------------------------------------


def test_runner_build_entry_produces_parallel_topology(temp_db):
    """create_compiled_app (the runner's build entry) yields fan-out topology.

    With the flip, the runner builds via create_compiled_app whose default is
    enable_parallel=True. The parallel target must be split into ``*_process``
    and ``*_aggregate`` nodes — proof the per-file fan-out is what runs.
    """
    app, _ = create_compiled_app(_parallel_workflow(), db_path=temp_db)
    nodes, _edges = _graph_topology(app)

    assert "Transcribe_process" in nodes, (
        f"flip did NOT take effect — no fan-out process node. nodes={sorted(nodes)}"
    )
    assert "Transcribe_aggregate" in nodes, (
        f"flip did NOT take effect — no fan-out aggregate node. nodes={sorted(nodes)}"
    )
    # The bare sequential node name must NOT exist when parallel is on.
    assert "Transcribe" not in nodes


def test_runner_source_passes_enable_parallel_true():
    """runner.py must pass enable_parallel=True to create_compiled_app.

    Source-level guard: catches a future edit that flips the live run path back
    to sequential (which would make the rendered diagram lie again).
    """
    runner_src = inspect.getsource(runner)
    assert "enable_parallel=True" in runner_src, (
        "runner.py no longer passes enable_parallel=True"
    )
    assert "enable_parallel=False" not in runner_src, (
        "runner.py still has an enable_parallel=False — the run path must stay "
        "parallel (#2532/#2541)"
    )


# ---------------------------------------------------------------------------
# 2. Bounded scheduling
# ---------------------------------------------------------------------------


def test_fan_out_send_payload_excludes_outputs_blob():
    """Each Send carries the trimmed payload only — never the full outputs blob.

    Locks the #2532 trim: copying ``outputs`` into every Send was a
    multiplicative RAM cost at large fan-out widths. The payload must contain
    the per-branch keys and library/task identity, and MUST NOT contain
    ``outputs``.
    """
    node_names = {"src": "Source", "tx": "Transcribe"}
    fan_out = _make_fan_out_function("src", ["tx"], node_names)

    state = {
        "outputs": {
            "src": {
                "files": ["/a.pdf", "/b.pdf", "/c.pdf"],
                "documents": [{"id": "d1"}, {"id": "d2"}, {"id": "d3"}],
            }
        },
        "task_id": "t",
        "workflow_id": "wf-flip",
        "library_path": "/lib",
    }

    sends = fan_out(state)
    assert len(sends) == 3, f"expected one Send per file, got {len(sends)}"
    for send in sends:
        assert send.node == "Transcribe_process"
        assert "outputs" not in send.arg, (
            "Send payload must NOT carry the full outputs blob (#2532 trim)"
        )
        # Trimmed payload still carries everything the parallel worker reads.
        assert set(send.arg) >= {
            "parallel_file",
            "parallel_document",
            "parallel_index",
            "parallel_total",
            "library_path",
        }
        assert send.arg["parallel_total"] == 3


def test_state_outputs_drop_redundant_per_file_arrays():
    """State keeps the aggregate text, not the full per-file arrays (#2541)."""
    merged = _merge_outputs(
        {},
        {
            "tx": {
                "text": "page 1\n\npage 2",
                "texts": ["page 1", "page 2"],
                "results": [{"file": "a"}, {"file": "b"}],
                "values": ["v1", "v2"],
                "records": [{"doc_id": "d1", "text": "page 1"}],
            }
        },
    )

    tx = merged["tx"]
    assert tx["text"] == "page 1\n\npage 2"
    assert tx["text_count"] == 2
    assert tx["result_count"] == 2
    assert tx["value_count"] == 2
    assert "texts" not in tx
    assert "results" not in tx
    assert "values" not in tx


@pytest.mark.asyncio
async def test_parallel_fan_out_bounds_concurrency(temp_db, monkeypatch):
    """A large file list does not run all branches at once.

    Fans out far more files than the concurrency cap and asserts the number of
    simultaneously in-flight parallel tool bodies never exceeds
    VISION_FAN_OUT_CONCURRENCY — the semaphore (not the Send count) is what
    bounds peak heavy memory, so this scales to thousands of files.
    """
    n_files = VISION_FAN_OUT_CONCURRENCY * 5  # 20 files, well over the cap of 4
    files = [f"/scan-{i}.pdf" for i in range(n_files)]
    documents = [{"id": f"page-{i}", "path": files[i]} for i in range(n_files)]

    in_flight = 0
    peak_in_flight = 0

    async def fake_files(*, inputs=None, state=None, llm_config=None, **_kw):
        return {"files": list(files), "documents": list(documents)}

    async def fake_transcribe(*, inputs=None, state=None, llm_config=None, **_kw):
        nonlocal in_flight, peak_in_flight
        in_flight += 1
        peak_in_flight = max(peak_in_flight, in_flight)
        try:
            # Yield so siblings would overlap if the semaphore did not throttle.
            await asyncio.sleep(0.02)
            doc = (inputs or {}).get("documents") or [None]
            doc_id = doc[0].get("id") if isinstance(doc[0], dict) else None
            return {"text": f"t::{doc_id}", "artifacts": [{"document_id": doc_id}]}
        finally:
            in_flight -= 1

    async def fake_sink(*, inputs=None, state=None, llm_config=None, **_kw):
        return {"downstream_ran": True}

    monkeypatch.setitem(registry.TOOLS, "files", fake_files)
    monkeypatch.setitem(registry.TOOLS, "transcribe", fake_transcribe)
    monkeypatch.setitem(registry.TOOLS, "aggregate", fake_sink)

    checkpointer = AsyncDuckDBCheckpointer.from_db_path(temp_db)
    app = build_graph(
        _parallel_workflow(),
        enable_parallel=True,
        checkpointer=checkpointer,
        skip_cache=True,
    )
    config = {"configurable": {"thread_id": "t-bound", "checkpoint_ns": ""}}
    initial_state = {
        "workflow_id": "wf-flip",
        "library_path": "",
        "inputs": {},
        "selected_doc_ids": [],
    }

    await _drive(app, initial_state, config)

    # Every file processed exactly once...
    snapshot = await app.aget_state(config)
    artifacts = snapshot.values.get("outputs", {}).get("tx", {}).get("artifacts", [])
    assert len(artifacts) == n_files, (
        f"expected {n_files} per-file results, got {len(artifacts)}"
    )
    # ...but never more than the cap in flight at once.
    assert peak_in_flight <= VISION_FAN_OUT_CONCURRENCY, (
        f"semaphore did not bound fan-out: peak {peak_in_flight} in-flight "
        f"exceeded cap {VISION_FAN_OUT_CONCURRENCY}"
    )
    # Sanity: the run actually overlapped branches (otherwise the bound is vacuous).
    assert peak_in_flight > 1, (
        "fan-out never overlapped — concurrency bound assertion would be vacuous"
    )


# ---------------------------------------------------------------------------
# 3. preview == run topology
# ---------------------------------------------------------------------------


def test_preview_and_run_topology_match(temp_db):
    """The diagram graph and the executed graph have identical topology.

    The runner renders the diagram from ``build_graph(wf, enable_parallel=True)``
    (runner.py preview) and executes the graph from ``create_compiled_app(wf)``
    (runner.py run, now enable_parallel=True). With the flip, both are parallel,
    so the rendered Mermaid matches what runs — "the diagram lies" cannot
    silently reopen.
    """
    workflow = _parallel_workflow()

    preview_app = build_graph(workflow, enable_parallel=True, checkpointer=None)
    run_app, _ = create_compiled_app(workflow, db_path=temp_db)

    preview_nodes, preview_edges = _graph_topology(preview_app)
    run_nodes, run_edges = _graph_topology(run_app)

    assert preview_nodes == run_nodes, (
        "preview vs run NODE topology diverged — the diagram would lie.\n"
        f"preview-only={sorted(preview_nodes - run_nodes)}\n"
        f"run-only={sorted(run_nodes - preview_nodes)}"
    )
    assert preview_edges == run_edges, (
        "preview vs run EDGE topology diverged — the diagram would lie.\n"
        f"preview-only={sorted(preview_edges - run_edges)}\n"
        f"run-only={sorted(run_edges - preview_edges)}"
    )
    # And the matching topology is the PARALLEL one (guards against both paths
    # silently collapsing to sequential together).
    assert "Transcribe_process" in run_nodes and "Transcribe_aggregate" in run_nodes
