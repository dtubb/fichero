"""What a workflow can be RUN ON — the engine's answer, not the client's.

Feeds the capability toolbar: given what the user has selected, show the
verbs that accept it. Served for the same reason as ``requires_vision`` —
a client re-deriving it reads the parent's nodes only and gets delegating
workflows wrong, and the summary list payload has no nodes to derive from.
"""

from __future__ import annotations

import json
import pathlib

from fichero_server.workflows.validation import (
    INPUT_KIND_DOCUMENTS,
    INPUT_KIND_TEXT,
    _entry_tool_nodes,
    workflow_input_kinds,
)

PRESETS = (
    pathlib.Path(__file__).resolve().parents[3]
    / "src/fichero_server/resources/default_workflows"
)


def _preset(name: str) -> dict:
    for path in PRESETS.glob("*.json"):
        data = json.loads(path.read_text())
        if data.get("name") == name:
            return data
    raise AssertionError(f"preset not found: {name}")


class TestEntryDetection:
    def test_a_downstream_text_tool_does_not_make_the_workflow_text_addressable(self):
        # Clean Up Text is files -> transcribe -> clean_text. clean_text takes
        # text, but it is fed BY transcribe, so the workflow as a whole wants
        # pixels. Unioning every tool's ports would wrongly offer this verb on
        # a highlighted passage.
        workflow = _preset("Clean Up Text")
        entries = [n["tool"] for n in _entry_tool_nodes(workflow["nodes"], workflow["edges"])]

        assert entries == ["transcribe"]
        assert workflow_input_kinds(workflow["nodes"], workflow["edges"]) == [
            INPUT_KIND_DOCUMENTS
        ]

    def test_source_nodes_are_not_entries(self):
        workflow = _preset("Clean Up Text")
        entries = [n["tool"] for n in _entry_tool_nodes(workflow["nodes"], workflow["edges"])]
        assert "files" not in entries, "a source says WHERE input comes from, not what kind"


class TestAcceptedKinds:
    def test_every_workflow_accepts_documents(self):
        # Every preset has a source node that resolves to files, so pointing
        # one at selected documents is always meaningful.
        for path in PRESETS.glob("*.json"):
            data = json.loads(path.read_text())
            kinds = workflow_input_kinds(data.get("nodes"), data.get("edges"))
            assert INPUT_KIND_DOCUMENTS in kinds, data.get("name")

    def test_a_text_entry_tool_makes_the_workflow_text_addressable(self):
        # Catalogue's entry tool has a literal `text` input port, so a passage
        # selected in the Reader can be handed straight to it.
        workflow = _preset("Catalogue")
        assert INPUT_KIND_TEXT in workflow_input_kinds(
            workflow["nodes"], workflow["edges"]
        )

    def test_a_vision_workflow_is_never_text_addressable(self):
        workflow = _preset("Paleografía Española (s. XVI–XVII)")
        assert workflow_input_kinds(workflow["nodes"], workflow["edges"]) == [
            INPUT_KIND_DOCUMENTS
        ]


class TestDegradedGraphs:
    def test_an_unreadable_graph_still_offers_documents(self):
        # Never strip every verb from the bar because a graph did not parse.
        assert workflow_input_kinds(None, None) == [INPUT_KIND_DOCUMENTS]
        assert workflow_input_kinds([{"tool": "nonexistent_tool"}], []) == [
            INPUT_KIND_DOCUMENTS
        ]

    def test_missing_edges_fall_back_to_treating_every_tool_as_an_entry(self):
        # With no edges we cannot tell what feeds what; reporting "no entries"
        # would silently drop the workflow's real capability.
        workflow = _preset("Clean Up Text")
        entries = [n["tool"] for n in _entry_tool_nodes(workflow["nodes"], None)]
        assert set(entries) == {"transcribe", "clean_text"}
