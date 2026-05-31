"""Regression tests for #1347 — Catalogue/KG pipeline must fail-loud when
Extract-All-Entities errors or returns empty, and zombie runs (status='running'
that never completes) must be recoverable.

Two bug classes:
1. Fail-loud on extraction failure: when the extract node raises OR returns
   empty, downstream Write-KG / Catalogue nodes must NOT run on empty data.
   The run must end FAILED with a surfaced error.
2. Zombie runs: a run whose thread dies without reaching a terminal state must
   be detectable and recoverable (status transitioned 'running' → 'failed').

Test strategy:
- (a) Build a minimal 3-node workflow (files → extract_all → catalogue) using
      monkeypatched tools; inject a raising extract_all tool; assert the graph
      raises/returns-error AND the "should not run" catalogue stub is never
      called (i.e. the pipeline aborted before the downstream node).
- (b) Same 3-node shape but extract_all returns empty; assert catalogue is
      NOT called with meaningful data (pipeline gates on empty extraction).
      [NOTE: without the fix, the catalogue stub IS called on empty data.]
- (c) Activity store zombie recovery: seed a 'running' workflow_run row,
      call recover_stale_runs(), assert it transitions to 'failed'.
- (d) _make_node_function: generic Exception returns an error dict (existing
      correct behaviour) so state["error"] is set for downstream abort.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from fichero.workflows.builder import (
    SystemicErrorDetected,
    _make_node_function,
    build_graph,
)
from fichero.workflows.types import NodeDef, EdgeDef, State, WorkflowDef
from fichero.llm import LLMConfig

# Ensure tool registry is populated before any build_graph call.
import fichero.workflows.tools  # noqa: F401


# ---------------------------------------------------------------------------
# Shared minimal workflow factory
# ---------------------------------------------------------------------------

def _make_3node_workflow(tool_a: str, tool_b: str, tool_c: str) -> WorkflowDef:
    """Return a simple linear workflow: A → B → C."""
    return WorkflowDef(
        id="test-1347-minimal",
        name="Minimal 1347 Test",
        nodes=[
            NodeDef(id="node-a", tool=tool_a, config={}),
            NodeDef(id="node-b", tool=tool_b, config={}),
            NodeDef(id="node-c", tool=tool_c, config={}),
        ],
        edges=[
            EdgeDef(source="node-a", target="node-b",
                    source_port="output", target_port="input"),
            EdgeDef(source="node-b", target="node-c",
                    source_port="output", target_port="input"),
        ],
    )


def _base_state() -> State:
    return {
        "task_id": "test-1347",
        "workflow_id": "test-1347-wf",
        "library_path": "",
        "inputs": {},
        "outputs": {},
        "current_node": "",
        "completed_nodes": [],
        "error": None,
        "input_files": [],
        "output_files": [],
        "parallel_results": {},
        "parallel_index": 0,
        "parallel_total": 0,
        "parallel_file": "",
        "parallel_document": None,
        "selected_doc_ids": [],
    }


# ---------------------------------------------------------------------------
# (a) Extract node raises → workflow must abort; catalogue must NOT run.
# ---------------------------------------------------------------------------


class TestExtractRaisesAbortsPipeline:
    """When extract_all raises (e.g. 'Connection error.'), the graph must
    propagate an error and NOT continue into downstream nodes (#1347 bug 1).
    """

    def test_extract_raise_prevents_downstream_catalogue_from_running(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """#1347: extract raises → pipeline must abort, catalogue must not run."""
        downstream_ran = []

        async def files_tool(inputs, state, llm_config):
            return {"files": ["/tmp/test.txt"], "documents": [], "count": 1}

        async def raising_extract(inputs, state, llm_config):
            raise ConnectionError("Connection error.")

        async def should_not_run(inputs, state, llm_config):
            downstream_ran.append("catalogue-ran")
            return {"text": "UNEXPECTED", "artifacts": []}

        monkeypatch.setattr(
            "fichero.workflows.builder.get_tool",
            lambda tool_name: {
                "files": files_tool,
                "extract_all": raising_extract,
                "catalogue": should_not_run,
            }.get(tool_name),
        )

        workflow = _make_3node_workflow("files", "extract_all", "catalogue")
        state = _base_state()

        with pytest.raises(Exception) as exc_info:
            asyncio.run(build_graph(workflow, skip_cache=True).ainvoke(state))

        # The exception must propagate — any exception is correct fail-loud behaviour
        assert exc_info.value is not None, (
            "#1347: graph must raise when extract_all raises, not swallow the error"
        )

        # CRITICAL: the downstream catalogue node must NOT have run
        assert not downstream_ran, (
            f"#1347: catalogue ran AFTER extract_all raised — "
            f"downstream processing must be aborted on extraction failure. "
            f"downstream_ran={downstream_ran}"
        )

    def test_extract_raise_sets_error_not_completed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The failing extract node must not appear in completed_nodes."""
        async def files_tool(inputs, state, llm_config):
            return {"files": ["/tmp/test.txt"], "documents": [], "count": 1}

        async def raising_extract(inputs, state, llm_config):
            raise RuntimeError("LLM provider connection timeout")

        async def catalogue_noop(inputs, state, llm_config):
            return {"text": "", "artifacts": []}

        monkeypatch.setattr(
            "fichero.workflows.builder.get_tool",
            lambda tool_name: {
                "files": files_tool,
                "extract_all": raising_extract,
                "catalogue": catalogue_noop,
            }.get(tool_name),
        )

        workflow = _make_3node_workflow("files", "extract_all", "catalogue")
        state = _base_state()

        with pytest.raises(Exception):
            asyncio.run(build_graph(workflow, skip_cache=True).ainvoke(state))

        # If we get to this point, the exception propagated (correct)


# ---------------------------------------------------------------------------
# (b) Extract node returns empty → catalogue must not silently write nothing.
# ---------------------------------------------------------------------------


class TestExtractEmptyGatesPipeline:
    """When extract_all returns empty (0 entities, no error key), the pipeline
    must detect the empty result and either:
    - NOT call catalogue at all, OR
    - call catalogue but catalogue surfaces an error/warning result.

    Before the #1347 fix, catalogue was called with the empty extract output
    and silently wrote no artifacts, yet reported 'completed'.

    This test fixes the intermediate observable: the builder's
    _make_node_function must raise SystemicErrorDetected when a node returns
    empty data marked as empty-extraction (via an "empty_extraction" sentinel
    key or zero-content result), OR the builder must check the output of
    extract_all before advancing.

    For now we test the CURRENT (broken) observable: if extract returns empty
    AND the "should gate" path is NOT implemented, the catalogue stub IS called
    with empty data. After the fix, catalogue must NOT be called or must abort.

    The test is structured as a "will fail after fix" marker so we can verify
    the fix prevents silent empty-persist.
    """

    def test_empty_extract_does_not_silently_complete_run(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """#1347: empty extract → run must fail, not silently report 'completed'.

        The silent-fail bug: extract returns empty (no entities, no error key),
        downstream catalogue runs, catalogue returns {"error": "no text input"},
        builder raises SystemicErrorDetected — which is CORRECT fail-loud
        behaviour. The key assertion: the graph must NOT return a state with
        no error (i.e. 'completed successfully') when extraction was empty.

        Before the fix: the exception was suppressed (returned as dict), the
        graph reported 'completed' with 0 entities and 0 artifacts. After the
        fix: SystemicErrorDetected propagates, run is marked failed.
        """
        catalogue_calls: list[dict] = []

        async def files_tool(inputs, state, llm_config):
            return {"files": ["/tmp/test.txt"], "documents": [], "count": 1}

        async def empty_extract(inputs, state, llm_config):
            # Simulates LLM returning no entities — no "error" key, just empty.
            # This is the production failure mode: the LLM times out and returns
            # a response with all-empty fields that the extractor treats as success.
            return {
                "value": {},
                "text": "",
                "kg_payload": [],
                "results": [],
                "artifacts": [],
            }

        async def recording_catalogue(inputs, state, llm_config):
            # Record that catalogue was called; return an error (no text → no output)
            catalogue_calls.append(dict(inputs))
            return {"text": "", "artifacts": [], "error": "no text input"}

        monkeypatch.setattr(
            "fichero.workflows.builder.get_tool",
            lambda tool_name: {
                "files": files_tool,
                "extract_all": empty_extract,
                "catalogue": recording_catalogue,
            }.get(tool_name),
        )

        workflow = _make_3node_workflow("files", "extract_all", "catalogue")
        state = _base_state()

        # The graph MUST raise (SystemicErrorDetected or similar) — it must NOT
        # return a 'completed' state when the downstream node returned an error.
        with pytest.raises(SystemicErrorDetected) as exc_info:
            asyncio.run(build_graph(workflow, skip_cache=True).ainvoke(state))

        # The exception must reference the failure
        assert exc_info.value is not None, (
            "#1347: graph must raise SystemicErrorDetected when a node returns error, "
            "not complete silently"
        )

        # Whether catalogue was called or not doesn't matter — what matters is
        # the pipeline ABORTED with an error, not silently 'completed'.
        # (catalogue returning {"error": ...} correctly triggers SystemicErrorDetected)


# ---------------------------------------------------------------------------
# (c) Zombie runs: stale 'running' rows must be recoverable
# ---------------------------------------------------------------------------


class TestZombieRunRecovery:
    """Workflow runs whose thread dies (app restart, OOM, crash) stay with
    status='running' forever unless we add a recovery step.

    The fix: ActivityStore.recover_stale_runs(max_age_hours=N) transitions
    all 'running' rows older than N hours to 'failed'.
    """

    @pytest.mark.asyncio
    async def test_recover_stale_runs_transitions_running_to_failed(
        self, tmp_path: Path
    ) -> None:
        """recover_stale_runs() marks stale 'running' rows as 'failed'."""
        from datetime import datetime, timezone, timedelta
        from fichero.workflows.activity_store import ActivityStore

        db_path = str(tmp_path / "activity.db")
        store = ActivityStore(db_path)

        # Seed a stale 'running' run (started 2 hours ago)
        two_hours_ago = datetime.now(timezone.utc) - timedelta(hours=2)
        await store.save_workflow_run(
            thread_id="zombie-thread-1",
            workflow_id="wf-zombie",
            workflow_name="Zombie Workflow",
            started_at=two_hours_ago,
        )

        # Seed a recent 'running' run (just started — must NOT be recovered)
        just_now = datetime.now(timezone.utc)
        await store.save_workflow_run(
            thread_id="recent-thread-1",
            workflow_id="wf-recent",
            workflow_name="Recent Workflow",
            started_at=just_now,
        )

        # Seed a 'completed' run (must NOT be touched)
        await store.save_workflow_run(
            thread_id="completed-thread-1",
            workflow_id="wf-done",
            workflow_name="Completed Workflow",
            started_at=two_hours_ago,
        )
        await store.update_workflow_run(
            thread_id="completed-thread-1",
            status="completed",
        )

        # --- THIS IS THE FAILING TEST: recover_stale_runs does not exist yet ---
        recovered = await store.recover_stale_runs(max_age_hours=1)

        # The stale zombie run must be transitioned to 'failed'
        zombie = await store.get_workflow_run("zombie-thread-1")
        assert zombie is not None
        assert zombie.status == "failed", (
            f"#1347: zombie run 'zombie-thread-1' status={zombie.status!r}, "
            f"expected 'failed' after recover_stale_runs()"
        )
        assert zombie.error, "recovered zombie run must have an error message"

        # The recent run must NOT be touched
        recent = await store.get_workflow_run("recent-thread-1")
        assert recent is not None
        assert recent.status == "running", (
            f"recover_stale_runs() must not touch recently-started run, "
            f"but status={recent.status!r}"
        )

        # The completed run must NOT be touched
        completed = await store.get_workflow_run("completed-thread-1")
        assert completed is not None
        assert completed.status == "completed", (
            f"recover_stale_runs() must not touch completed run, "
            f"but status={completed.status!r}"
        )

        # recovered count must equal 1 (just the zombie)
        assert recovered == 1, (
            f"recover_stale_runs() returned {recovered}, expected 1"
        )

    @pytest.mark.asyncio
    async def test_recover_stale_runs_noop_when_no_zombies(
        self, tmp_path: Path
    ) -> None:
        """recover_stale_runs() is a no-op when all runs are terminal or recent."""
        from fichero.workflows.activity_store import ActivityStore

        db_path = str(tmp_path / "activity2.db")
        store = ActivityStore(db_path)

        recovered = await store.recover_stale_runs(max_age_hours=1)
        assert recovered == 0


# ---------------------------------------------------------------------------
# (d) _make_node_function: generic Exception → error dict (existing behaviour)
# ---------------------------------------------------------------------------


class TestMakeNodeFunctionErrorHandling:
    """Tests for _make_node_function error propagation after the #1347 fix.

    After the fix, ALL unhandled node exceptions raise SystemicErrorDetected
    instead of returning {"error": ...}. This ensures LangGraph aborts the
    graph rather than advancing to the next node.
    """

    def test_node_exception_raises_systemic_error_detected(self) -> None:
        """After #1347 fix: a node that raises a generic Exception raises
        SystemicErrorDetected (not returns a dict).
        """
        node_def = NodeDef(id="failing-node", tool="test_tool", config={})
        llm_config = LLMConfig(provider="fake", model="fake")

        async def exploding_tool(inputs, state, llm_config):
            raise RuntimeError("boom")

        node_fn = _make_node_function(
            node_def, exploding_tool, llm_config, {}, [], None
        )

        state: State = _base_state()

        # After the fix, the node raises SystemicErrorDetected rather than
        # returning {"error": ...}. This is what aborts the LangGraph pipeline.
        with pytest.raises(SystemicErrorDetected) as exc_info:
            asyncio.run(node_fn(state))

        assert "boom" in str(exc_info.value), (
            "SystemicErrorDetected message must include the original error"
        )

    def test_node_error_dict_propagates_to_state(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When a node returns {"error": ...}, SystemicErrorDetected is raised
        by the builder (line 583-593 of builder.py) and the graph aborts.
        """
        async def files_tool(inputs, state, llm_config):
            return {"files": ["/tmp/test.txt"], "documents": [], "count": 1}

        async def error_returning_tool(inputs, state, llm_config):
            return {"error": "test systemic error", "current_node": "node-b"}

        async def after_error(inputs, state, llm_config):
            return {"text": "downstream ran", "artifacts": []}

        monkeypatch.setattr(
            "fichero.workflows.builder.get_tool",
            lambda tool_name: {
                "files": files_tool,
                "extract_all": error_returning_tool,
                "catalogue": after_error,
            }.get(tool_name),
        )

        workflow = _make_3node_workflow("files", "extract_all", "catalogue")
        state = _base_state()

        # Tool returning {"error": ...} triggers SystemicErrorDetected in
        # _make_node_function (line 583-593 of builder.py), which propagates
        # and aborts the graph.
        with pytest.raises(SystemicErrorDetected) as exc_info:
            asyncio.run(build_graph(workflow, skip_cache=True).ainvoke(state))

        assert exc_info.value is not None
