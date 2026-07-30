"""The silent-run guard on the entity surface, in BOTH directions (#4379 #4283).

Making `_detect_empty_text_output` reachable for named-entity runs (declaring
the `files` channel + publishing the source node's list) is only half a fix.
The other half is the guard staying USEFUL once it can fire: entity tools
produce no text, no artifacts and no results rows, so without teaching the
detector what entity-shaped output looks like it would flag every successful
NER run — and a guard that cries wolf on success is worse than one that never
fires, because the next genuine silent failure gets ignored.

The coverage lane pins the positive direction (a successful NER run must not
be flagged). These pin the NEGATIVE direction, which is the half that actually
implements #4283 for entities: a run that read every document and produced
nothing must still be caught. Nothing here skips.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.integration._seedlib import seed

from fichero_server.db import db_manager
from fichero_server.execution.runner import _detect_empty_text_output
from fichero_server.models import DocType, Document, FileType
from fichero_server.workflows.types import State


def _state(summary: dict | None, *, files: list[str] | None = None) -> dict:
    """A terminal state shaped like a one-node entity run."""
    node_output: dict = {"count": 0}
    if summary is not None:
        node_output["summary"] = summary
    return {
        "files": files if files is not None else ["/tmp/page-1.txt"],
        "outputs": {"extract-entities": node_output},
    }


_NOTHING_HAPPENED = {
    "documents_processed": 24,
    "entity_mentions_processed": 0,
    "entities_created": 0,
    "entities_reused": 0,
    "entities_suppressed": 0,
}


class TestSilentEntityRunIsStillCaught:
    def test_run_that_read_everything_and_produced_nothing_is_flagged(self):
        """The #4283 shape, on the entity surface: 24 documents in, zero
        entities out, no error anywhere. That is a failure, not a success."""
        is_empty, reason = _detect_empty_text_output(_state(_NOTHING_HAPPENED))
        assert is_empty, (
            "a NER run that processed 24 documents and produced no entities "
            "reported no output at all — it must not read as a green success"
        )
        assert reason, "a flagged run must say what went wrong"

    def test_documents_processed_alone_does_not_count_as_output(self):
        """Reading a document is not producing anything.

        The tempting fix is to treat `documents_processed` (or `count`) as
        proof of work — it would make the successful-run test pass just as
        well, and would silently disable #4283 for every entity run.
        """
        summary = {"documents_processed": 500, "entities_created": 0}
        is_empty, _ = _detect_empty_text_output(_state(summary))
        assert is_empty, (
            "documents_processed must not be mistaken for observable output"
        )

    def test_node_error_is_named_in_the_reason(self):
        state = _state(_NOTHING_HAPPENED)
        state["outputs"]["extract-entities"]["error"] = "no entity-capable model"
        is_empty, reason = _detect_empty_text_output(state)
        assert is_empty
        assert "no entity-capable model" in reason


class TestRealEntityWorkIsNotFlagged:
    @pytest.mark.parametrize(
        "summary",
        [
            pytest.param({"entities_created": 2}, id="created"),
            pytest.param({"entities_reused": 5}, id="reused"),
            pytest.param({"entity_mentions_processed": 1}, id="mentions"),
            pytest.param({"claims_extracted": 3}, id="svo-claims"),
            pytest.param({"claims_created": 1}, id="svo-created"),
            pytest.param({"claims_reused": 1}, id="svo-reused"),
        ],
    )
    def test_any_real_entity_or_claim_work_counts_as_output(self, summary):
        is_empty, reason = _detect_empty_text_output(_state(summary))
        assert not is_empty, (
            f"{summary} is real knowledge-graph output but was flagged ({reason!r})"
        )


class TestGuardIsRobust:
    def test_non_numeric_summary_values_do_not_crash_the_guard(self):
        """A summary is tool-authored data; the guard must never be the thing
        that breaks a run boundary."""
        summary = {"entities_created": "two", "entities_reused": None}
        is_empty, _ = _detect_empty_text_output(_state(summary))
        assert is_empty, "unparseable counts are not evidence of output"

    def test_summary_that_is_not_a_mapping_is_ignored(self):
        state = _state(None)
        state["outputs"]["extract-entities"]["summary"] = "all done!"
        is_empty, _ = _detect_empty_text_output(state)
        assert is_empty

    def test_no_input_workflow_is_still_exempt(self):
        """#2244/#2245: a workflow that legitimately consumes no files must
        never be flagged, however empty its output."""
        is_empty, _ = _detect_empty_text_output(_state(_NOTHING_HAPPENED, files=[]))
        assert not is_empty


class TestFilesIsADeclaredChannel:
    """The enabling seam. `files` was read in three places and written by the
    fan-out sub-states, but was never declared on ``State`` — so LangGraph
    dropped every top-level write and no terminal state ever carried it. That
    is what made the guard structurally unreachable, and a plain dict-write
    test would NOT have caught it, because the drop happens in the graph.
    """

    def test_state_declares_files(self):
        assert "files" in State.__annotations__, (
            "`files` must be a declared channel or LangGraph silently drops "
            "every write to it (#4379)"
        )

    def test_a_source_node_publishes_its_files_into_the_terminal_state(
        self, tmp_path: Path
    ):
        """End-to-end through a real graph: the drop was invisible anywhere else."""
        import asyncio

        from fichero_server.workflows.builder import build_graph
        from fichero_server.workflows.runtime import build_initial_state
        from fichero_server.workflows.types import NodeDef, WorkflowDef

        library_path = tmp_path / "files-channel.fichero"
        seed(library_path)
        db = db_manager.get_database(library_path)

        folder = Document(id="fc-folder", name="corpus", doc_type=DocType.folder)
        db.save(folder)
        source_file = tmp_path / "page-1.txt"
        source_file.write_text("Regression Person in Regression Place.", "utf-8")
        db.save(
            Document(
                id="fc-doc-1",
                parent_id=folder.id,
                name=source_file.name,
                path=str(source_file),
                doc_type=DocType.file,
                file_type=FileType.text,
                page_content="Regression Person in Regression Place.",
            )
        )

        workflow = WorkflowDef(
            id="files-channel-wf",
            name="Files only",
            nodes=[NodeDef(id="files-source", tool="files", config={})],
            edges=[],
        )
        state = build_initial_state(
            {"selected_doc_ids": [folder.id]}, library_path=str(library_path)
        )
        state["task_id"] = "files-channel-run"
        final_state = asyncio.run(build_graph(workflow, skip_cache=True).ainvoke(state))

        assert final_state.get("files"), (
            "a source node's resolved file list did not survive into the "
            "terminal state — the `files` channel is being dropped again, and "
            "with it #4283's guard on every per-document preset (#4379)"
        )
