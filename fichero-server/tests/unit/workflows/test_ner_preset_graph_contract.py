"""Structural contract for the two shipped named-entity-extraction presets
(#4379, #4369).

#4369 names the dangerous defect class: a graph that *passes preflight*, starts
running, and then dead-ends or drops a branch. Stub-based smoke runs never see
it because they never traverse the real graph shape. NER is the surface Daniel
is running right now (#4379), so its two presets get the structural proof
first:

- ``NER per-page (local)``      (ner_per_page_local.json)
- ``2 · Extract Entities``      (catalogue_stage_2_extract_entities.json)

What is pinned here, per #4369 work-item 1:
  * every node's tool is actually registered (a renamed tool must fail here,
    not mid-run),
  * every edge resolves to real nodes AND to *declared* ports on both ends,
  * no zero-edge preset,
  * no orphan node: every node is reachable from a source node,
  * every entry node reaches a terminal (no-outgoing-edge) node — the
    dead-end branch class from #4345 defect 3,
  * the extraction node is a terminal, i.e. the preset actually ends in
    entity extraction rather than trailing into an unwired stage.

These assertions are on graph topology and registry facts only — never on
descriptions or labels, which a reword would break.
"""

from __future__ import annotations

import pytest

from fichero_server.models import Workflow
from fichero_server.workflows.default_workflows import _load_preset_files
from fichero_server.workflows import registry as workflow_registry
from fichero_server.workflows.runtime import to_workflow_def
from fichero_server.workflows.validation import (
    validate_workflow_connections,
    validate_workflow_preflight,
)

# Import tools for registry side effects before any registry lookup.
import fichero_server.workflows.tools  # noqa: F401


NER_PRESET_NAMES = ["NER per-page (local)", "2 · Extract Entities"]

# The tool each preset must terminate in. If a preset is ever rewired so it
# no longer ends in entity extraction, that is a product change that must be
# a deliberate edit to this map, not a silent drift.
NER_TERMINAL_TOOL = {
    "NER per-page (local)": "extract_all",
    "2 · Extract Entities": "extract_entities_only",
}


def _preset(name: str) -> dict:
    presets = {p["name"]: p for p in _load_preset_files()}
    assert name in presets, (
        f"shipped preset {name!r} is missing — NER has no preset to run "
        f"(available: {sorted(presets)})"
    )
    return presets[name]


def _workflow_def(name: str):
    preset = _preset(name)
    return to_workflow_def(
        Workflow(
            id=f"ner-contract-{name}",
            name=preset["name"],
            description=preset.get("description", ""),
            nodes=preset["nodes"],
            edges=preset["edges"],
            config=preset.get("config", {}),
            folder_path=preset.get("folder_path", "/"),
        )
    )


@pytest.mark.parametrize("preset_name", NER_PRESET_NAMES)
class TestNerPresetGraphShape:
    def test_every_node_tool_is_registered(self, preset_name: str):
        preset = _preset(preset_name)
        missing = [
            node["tool"]
            for node in preset["nodes"]
            if workflow_registry.get_tool_def(node["tool"]) is None
        ]
        assert missing == [], (
            f"{preset_name}: nodes reference unregistered tools {missing} — "
            "the run would fail at dispatch"
        )

    def test_preset_has_at_least_one_edge(self, preset_name: str):
        preset = _preset(preset_name)
        assert preset["edges"], (
            f"{preset_name}: zero-edge preset (#4324) — nothing can flow"
        )

    def test_every_edge_resolves_to_real_nodes(self, preset_name: str):
        preset = _preset(preset_name)
        node_ids = {node["id"] for node in preset["nodes"]}
        dangling = [
            (edge["id"], edge["source"], edge["target"])
            for edge in preset["edges"]
            if edge["source"] not in node_ids or edge["target"] not in node_ids
        ]
        assert dangling == [], f"{preset_name}: edges reference unknown nodes {dangling}"

    def test_every_edge_uses_declared_ports_on_both_ends(self, preset_name: str):
        preset = _preset(preset_name)
        tool_by_node = {node["id"]: node["tool"] for node in preset["nodes"]}
        problems: list[str] = []
        for edge in preset["edges"]:
            source_def = workflow_registry.get_tool_def(tool_by_node[edge["source"]])
            target_def = workflow_registry.get_tool_def(tool_by_node[edge["target"]])
            assert source_def and target_def  # covered by the registry test above
            if edge["source_port"] not in {p.id for p in source_def.output_ports}:
                problems.append(
                    f"{edge['source']}.{edge['source_port']} is not a declared output"
                )
            if edge["target_port"] not in {p.id for p in target_def.input_ports}:
                problems.append(
                    f"{edge['target']}.{edge['target_port']} is not a declared input"
                )
        assert problems == [], f"{preset_name}: unwired ports (#4298): {problems}"

    def test_no_orphan_nodes(self, preset_name: str):
        """Every node must be reachable from a node with no incoming edge."""
        preset = _preset(preset_name)
        node_ids = {node["id"] for node in preset["nodes"]}
        targets = {edge["target"] for edge in preset["edges"]}
        entries = node_ids - targets
        assert entries, f"{preset_name}: no entry node — the graph is a cycle"

        adjacency: dict[str, set[str]] = {node_id: set() for node_id in node_ids}
        for edge in preset["edges"]:
            adjacency[edge["source"]].add(edge["target"])
            for routed in (edge.get("route_map") or {}).values():
                adjacency[edge["source"]].add(routed)

        reachable = set(entries)
        frontier = list(entries)
        while frontier:
            current = frontier.pop()
            for nxt in adjacency[current]:
                if nxt not in reachable:
                    reachable.add(nxt)
                    frontier.append(nxt)

        assert reachable == node_ids, (
            f"{preset_name}: orphan nodes never reached from an entry: "
            f"{sorted(node_ids - reachable)}"
        )

    def test_every_entry_node_reaches_a_terminal(self, preset_name: str):
        """#4345 defect 3: a branch that never reaches an exit hangs the run."""
        preset = _preset(preset_name)
        node_ids = {node["id"] for node in preset["nodes"]}
        adjacency: dict[str, set[str]] = {node_id: set() for node_id in node_ids}
        for edge in preset["edges"]:
            adjacency[edge["source"]].add(edge["target"])
            for routed in (edge.get("route_map") or {}).values():
                adjacency[edge["source"]].add(routed)
        terminals = {node_id for node_id, out in adjacency.items() if not out}
        assert terminals, f"{preset_name}: no terminal node — every node has an exit edge"

        entries = node_ids - {edge["target"] for edge in preset["edges"]}
        for entry in entries:
            seen = {entry}
            frontier = [entry]
            hit_terminal = False
            while frontier:
                current = frontier.pop()
                if current in terminals:
                    hit_terminal = True
                    break
                for nxt in adjacency[current]:
                    if nxt not in seen:
                        seen.add(nxt)
                        frontier.append(nxt)
            assert hit_terminal, (
                f"{preset_name}: entry node {entry!r} never reaches a terminal node"
            )

    def test_preset_terminates_in_entity_extraction(self, preset_name: str):
        preset = _preset(preset_name)
        sources = {edge["source"] for edge in preset["edges"]}
        terminal_tools = {
            node["tool"] for node in preset["nodes"] if node["id"] not in sources
        }
        assert NER_TERMINAL_TOOL[preset_name] in terminal_tools, (
            f"{preset_name}: does not end in "
            f"{NER_TERMINAL_TOOL[preset_name]!r} (terminals: {sorted(terminal_tools)})"
        )

    def test_clears_the_execute_validation_gate(self, preset_name: str, monkeypatch):
        """The same gate /execute applies, run against the NER presets."""
        from types import SimpleNamespace

        monkeypatch.delenv("FICHERO_LOCAL_ONLY", raising=False)
        for tier in ("SMALL", "MEDIUM", "LARGE"):
            monkeypatch.setenv(f"FICHERO_{tier}_PROVIDER", "apple")
            monkeypatch.setenv(f"FICHERO_{tier}_MODEL", "apple-intelligence")
            monkeypatch.setenv(f"FICHERO_VISION_{tier}_PROVIDER", "apple")
            monkeypatch.setenv(f"FICHERO_VISION_{tier}_MODEL", "apple-vision")
        monkeypatch.setattr(
            "fichero_server.db.app.get_app_db",
            lambda: SimpleNamespace(
                get_default_model_for_category=lambda _category: None,
                list_providers=lambda: [],
            ),
        )
        workflow_def = _workflow_def(preset_name)
        errors = [
            *validate_workflow_connections(workflow_def),
            *validate_workflow_preflight(workflow_def),
        ]
        assert errors == [], f"{preset_name}: fails the /execute gate: {errors}"


class TestNerPerPageKeepsPerRecordChunking:
    """The local NER preset concats every selected file into one text blob.

    The only thing keeping that from becoming a single unbounded prompt is
    the second edge: aggregate.records → extract_all.records, which makes
    extract_all chunk per source record instead of splitting one giant
    string. Dropping that edge silently converts the preset into a
    whole-corpus-in-one-prompt run — the memory/So-long-connection shape of
    #4379. Pin it.
    """

    def test_aggregate_feeds_records_not_only_text(self):
        preset = _preset("NER per-page (local)")
        aggregate_id = next(
            node["id"] for node in preset["nodes"] if node["tool"] == "aggregate"
        )
        extract_id = next(
            node["id"] for node in preset["nodes"] if node["tool"] == "extract_all"
        )
        ports = {
            (edge["source_port"], edge["target_port"])
            for edge in preset["edges"]
            if edge["source"] == aggregate_id and edge["target"] == extract_id
        }
        assert ("records", "records") in ports, (
            "aggregate must forward per-file records to extract_all so "
            "extraction chunks per record; without it the whole corpus "
            "becomes one prompt (#4379)"
        )
        assert ("text", "text") in ports, (
            "extract_all still needs the aggregated text input"
        )
