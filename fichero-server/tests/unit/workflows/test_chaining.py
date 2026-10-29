"""Unit tests for workflow chaining system."""

import pytest
from unittest.mock import MagicMock, patch

from fichero_server.workflows.builder import build_graph
from fichero_server.workflows.executor import WorkflowExecutor
from fichero_server.execution.chaining import (
    WorkflowChain,
    ChainStep,
    ChainStore,
)
from fichero_server.workflows.runtime import build_initial_state
from fichero_server.workflows.types import WorkflowDef, NodeDef, EdgeDef


# =============================================================================
# Test Chain Definition
# =============================================================================

class TestWorkflowChain:
    """Tests for WorkflowChain model."""

    def test_create_chain(self):
        """Test creating a workflow chain."""
        chain = WorkflowChain(
            name="Test Chain",
            description="A test chain",
            steps=[
                ChainStep(id="step1", workflow_id="wf1"),
                ChainStep(id="step2", workflow_id="wf2"),
            ],
        )
        assert chain.name == "Test Chain"
        assert len(chain.steps) == 2
        assert chain.id is not None

    def test_get_step(self):
        """Test getting step by ID."""
        chain = WorkflowChain(
            name="Test",
            steps=[
                ChainStep(id="s1", workflow_id="wf1"),
                ChainStep(id="s2", workflow_id="wf2"),
            ],
        )
        step = chain.get_step("s2")
        assert step is not None
        assert step.workflow_id == "wf2"



# =============================================================================
# Test Chain Store
# =============================================================================

class TestChainStore:
    """Tests for ChainStore."""

    def test_save_and_get(self):
        """Test saving and retrieving a chain."""
        store = ChainStore()
        chain = WorkflowChain(name="Test", steps=[])

        saved = store.save(chain)
        retrieved = store.get(saved.id)

        assert retrieved is not None
        assert retrieved.name == "Test"

    def test_list_chains(self):
        """Test listing chains."""
        store = ChainStore()
        store.save(WorkflowChain(name="Chain 1", steps=[]))
        store.save(WorkflowChain(name="Chain 2", steps=[]))
        store.save(WorkflowChain(name="Chain 3", steps=[]))

        chains = store.list(limit=2)
        assert len(chains) == 2

    def test_delete_chain(self):
        """Test deleting a chain."""
        store = ChainStore()
        chain = store.save(WorkflowChain(name="To Delete", steps=[]))

        assert store.delete(chain.id) is True
        assert store.get(chain.id) is None

    def test_delete_nonexistent(self):
        """Test deleting nonexistent chain returns False."""
        store = ChainStore()
        assert store.delete("nonexistent-id") is False



# =============================================================================
# The standalone executor's state (it still runs one workflow; the chain executor that drove it is retired, #4949)
# =============================================================================

def test_workflow_executor_initial_state_exposes_selection_inputs():
    """Legacy executor state must expose selection fields at top level."""
    workflow = MagicMock()
    workflow.id, workflow.name = "wf-test", "Test Workflow"
    with patch("fichero_server.workflows.executor.build_graph", return_value=MagicMock()):
        executor = WorkflowExecutor(workflow)

    state = executor._create_initial_state(
        {
            "selected_doc_ids": ["doc-1"],
            "library_path": "/tmp/test.fichero",
        }
    )

    assert state["selected_doc_ids"] == ["doc-1"]
    assert state["library_path"] == "/tmp/test.fichero"


# =============================================================================
# Workflow Runtime Regression
# =============================================================================

@pytest.mark.asyncio
async def test_reference_search_unavailable_is_empty_safe_for_transcribe_review(
    monkeypatch,
):
    """Optional reference search must not abort two-pass transcription workflows."""

    from fichero_server.workflows.tools.sources import search_tool

    captured: dict = {}

    async def transcribe_tool(inputs, state, llm_config):
        return {"text": "draft paleography transcription"}

    async def review_tool(inputs, state, llm_config):
        captured["context"] = inputs.get("context")
        captured["metadata"] = inputs.get("metadata")
        return {
            "text": "reviewed transcription",
            "metadata_count": len(inputs.get("metadata") or []),
        }

    monkeypatch.setattr(
        "fichero_server.workflows.builder.get_tool",
        lambda tool_name: {
            "transcribe": transcribe_tool,
            "search": search_tool,
            "transcribe_review": review_tool,
        }.get(tool_name),
    )

    class MissingReferenceIndexRetriever:
        def __init__(self, db):
            self.db = db

        def retrieve(self, **kwargs):
            raise RuntimeError(
                "Catalog Error: Table with name embeddings does not exist"
            )

    workflow = WorkflowDef(
        id="wf-reference-search-optional",
        name="Reference Search Optional",
        nodes=[
            NodeDef(id="transcribe", tool="transcribe", config={}),
            NodeDef(id="reference-search", tool="search", config={}),
            NodeDef(id="review", tool="transcribe_review", config={}),
        ],
        edges=[
            EdgeDef(
                source="transcribe",
                target="reference-search",
                source_port="text",
                target_port="query",
            ),
            EdgeDef(
                source="transcribe",
                target="review",
                source_port="text",
                target_port="context",
            ),
            EdgeDef(
                source="reference-search",
                target="review",
                source_port="documents",
                target_port="metadata",
            ),
        ],
    )

    with (
        patch("fichero_server.workflows.tools.sources.db_manager") as mock_manager,
        patch(
            "fichero_server.workflows.tools.sources.GraphAwareRetriever",
            MissingReferenceIndexRetriever,
        ),
    ):
        mock_manager.get_database.return_value = MagicMock()
        initial_state = build_initial_state({}, library_path="/tmp/test.fichero")
        initial_state["workflow_id"] = workflow.id
        final_state = await build_graph(workflow, enable_parallel=False).ainvoke(
            initial_state
        )

    assert final_state.get("error") is None
    assert captured["context"] == "draft paleography transcription"
    assert captured["metadata"] == []
    assert final_state["outputs"]["reference-search"]["documents"] == []
    assert final_state["outputs"]["reference-search"]["count"] == 0
    assert final_state["outputs"]["review"]["metadata_count"] == 0
    assert set(final_state.get("completed_nodes") or []) == {
        "transcribe",
        "reference-search",
        "review",
    }
