"""A source node must emit the container it read from (#4404 #4397 #4399).

`summarize_folder` declares a `folder_id` input port that no source tool could
fill: `folder_tool` took `folder_id` as *config* and never returned it, and
`_expand_folder` dissolved the folder into leaf descendants so its identity was
lost at the node boundary. The declared graph therefore had NO channel able to
carry a folder id, and the folder summary was generated, paid for, and silently
discarded on every run.

That missing channel is also why seventeen modules reach around the graph into
`state["selected_doc_ids"]` — it was the only place the information existed.

These pin the channel at both ends: the port is declared, and the runtime
actually populates it. A declared port that the tool never fills is exactly the
bug being fixed, so asserting the declaration alone would reproduce it.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from tests.integration._seedlib import seed

from fichero_server.db import db_manager
from fichero_server.llm import LLMConfig
from fichero_server.models import DocType, Document, FileType
from fichero_server.workflows.registry import get_tool_def
from fichero_server.workflows.tools.sources import collection_tool, folder_tool


@pytest.fixture(autouse=True)
def _no_default_workflow_seeding(monkeypatch):
    monkeypatch.setenv("FICHERO_SKIP_DEFAULT_WORKFLOWS", "1")


@pytest.fixture
def library(tmp_path: Path):
    package = tmp_path / "container-identity.fichero"
    seed(package)
    db = db_manager.get_database(package)

    folder = Document(id="ci-folder", name="Box 1", doc_type=DocType.folder)
    db.save(folder)
    for index in range(2):
        source_file = tmp_path / f"page-{index + 1}.txt"
        source_file.write_text("Regression Person in Regression Place.", "utf-8")
        db.save(
            Document(
                id=f"ci-doc-{index + 1}",
                parent_id=folder.id,
                name=source_file.name,
                path=str(source_file),
                doc_type=DocType.file,
                file_type=FileType.text,
                page_content="Regression Person in Regression Place.",
            )
        )
    return package, folder.id


def _output_port_ids(tool_name: str) -> set[str]:
    tool_def = get_tool_def(tool_name)
    assert tool_def is not None, f"{tool_name} is not registered"
    return {port.id for port in tool_def.output_ports}


class TestTheContainerPortIsDeclared:
    def test_folder_source_declares_folder_id(self):
        assert "folder_id" in _output_port_ids("folder"), (
            "without a declared container output port, a folder-scoped "
            "consumer can never be wired to its source on the canvas (#4404)"
        )

    def test_collection_source_declares_collection_id(self):
        assert "collection_id" in _output_port_ids("collection")

    def test_summarize_folder_input_can_now_be_satisfied(self):
        """The closed loop that made this a bug rather than a gap."""
        consumer = get_tool_def("summarize_folder")
        assert consumer is not None
        required = {port.id for port in consumer.input_ports}
        assert "folder_id" in required, "fixture stale — port renamed?"
        assert "folder_id" in _output_port_ids("folder"), (
            "summarize_folder declares a folder_id input; some source must be "
            "able to produce one or the node is unusable by construction"
        )


class TestTheContainerPortIsActuallyPopulated:
    """A declared port the tool never fills IS the bug — assert the runtime."""

    def test_folder_tool_returns_the_folder_it_read(self, library):
        package, folder_id = library
        result = asyncio.run(
            folder_tool(
                inputs={"folder_id": folder_id},
                state={"library_path": str(package)},
                llm_config=LLMConfig(provider="", model=""),
            )
        )
        assert result.get("folder_id") == folder_id, (
            "the folder source read a folder and did not say which one — its "
            "identity dies at the node boundary (#4404)"
        )
        assert result["count"] == 2, "precondition: the folder's files resolved"

    def test_collection_tool_returns_the_collection_it_read(self, library):
        package, folder_id = library
        result = asyncio.run(
            collection_tool(
                inputs={"collection_id": folder_id},
                state={"library_path": str(package)},
                llm_config=LLMConfig(provider="", model=""),
            )
        )
        assert result.get("collection_id") == folder_id

    def test_the_selection_override_branch_does_not_claim_a_collection(
        self, library
    ):
        """Honesty at the seam: when a UI selection overrides the configured
        collection, the node did NOT read that collection, so it must not
        report having done so. Emitting the ignored id would be a lie that a
        downstream consumer would attach output to."""
        package, folder_id = library
        result = asyncio.run(
            collection_tool(
                inputs={"collection_id": "some-other-collection"},
                state={
                    "library_path": str(package),
                    "selected_doc_ids": ["ci-doc-1"],
                },
                llm_config=LLMConfig(provider="", model=""),
            )
        )
        assert not result.get("collection_id"), (
            "the selection overrode the configured collection, so the node "
            "must not claim to have read it"
        )
