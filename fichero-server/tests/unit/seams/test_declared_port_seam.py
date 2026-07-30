"""Seam category 1 — declared workflow ports (#4420).

The archetype is #4404. ``summarize_folder`` declares a ``folder_id`` input
port. No source tool emitted a folder id, so the port could never be filled
by an edge: the node shipped, ran, and silently discarded the work it was
supposed to do on the folder the user selected. Both halves looked correct
alone — the tool declares what it needs, the sources declare what they have —
and nothing compared the two.

The rule:

    every declared INPUT port must be fillable by some tool's declared
    OUTPUT port, unless it is explicitly declared config-supplied.

That exception is unavoidable and is where the care goes. ``PortDef`` has no
flag distinguishing "fed by an edge" from "typed by the user into the node's
config" (id, name, port_type, data_type, required, description, default —
nothing more). So the sweep cannot infer intent, and a naive assertion flags
~46 tools for ``context`` and ``metadata`` alone, which is noise, not signal.

``CONFIG_SUPPLIED_PORTS`` therefore names each legitimately edge-less port
with a reason, and ``test_allowlist_has_no_stale_entries`` keeps it honest in
both directions: an entry that becomes fillable, or that matches no port at
all, fails. Without that, the allowlist would quietly become the second place
defects hide.

DELIBERATELY NOT ASSERTED — the output half. #4420 phrases it as "every
declared output is consumed by something **or is a terminal**", and since
almost any output may legitimately be a terminal, the assertion admits ~52
ports with no way to separate a real orphan from a normal endpoint. One
precise assertion beats two noisy ones; the output half needs a definition of
"terminal" grounded in the shipped presets before it is worth writing, and is
left for a later pass rather than shipped as noise.

Findings are reported, not fixed (#4420).
"""

from __future__ import annotations

import pytest

# Registry side effects: every tool must be imported before it is inspected.
import fichero_server.workflows.tools  # noqa: F401
from fichero_server.workflows import registry as workflow_registry

# Input ports filled from node config or run inputs rather than an upstream
# edge. Every entry needs a reason; the hygiene test keeps them true.
CONFIG_SUPPLIED_PORTS: dict[str, str] = {
    "context": "free-text context typed into the node's config by the user",
    "metadata": "per-node metadata supplied in config, not produced upstream",
    "prompt": "the user's prompt for model_comparison, typed in config",
    "system_prompt": "system prompt typed in config",
    "task": "the instruction given to an agent tool, typed in config",
    "query": "search text typed by the user into the node's config",
    "input": "generic entry port on control-flow nodes (if/switch/custom_llm/sub_workflow)",
    "items": "collection supplied by the surrounding loop/filter construct",
    "input_1": "merge node's numbered inlets, wired positionally by the editor",
    "input_2": "merge node's numbered inlets, wired positionally by the editor",
    "input_3": "merge node's numbered inlets, wired positionally by the editor",
    "barrier": "dependency-only sync port; carries no data by design",
    "anchor_printed_page": "book_index_extract calibration value entered by the user",
    "anchor_sequence": "book_index_extract calibration value entered by the user",
    "index_start_sequence": "book_index_extract page range entered by the user",
    "index_end_sequence": "book_index_extract page range entered by the user",
    "page_offset": "book_index_extract offset entered by the user",
}


def _tool_defs() -> dict:
    return dict(workflow_registry.TOOL_DEFS)


def _output_port_ids() -> set[str]:
    return {
        port.id for td in _tool_defs().values() for port in td.output_ports
    }


def _unfillable_inputs() -> dict[str, list[str]]:
    """input port id -> ['tool(required=…)', …] for ports no output can fill."""
    outputs = _output_port_ids()
    unfillable: dict[str, list[str]] = {}
    for name, td in sorted(_tool_defs().items()):
        for port in td.input_ports:
            if port.id in outputs or port.id in CONFIG_SUPPLIED_PORTS:
                continue
            unfillable.setdefault(port.id, []).append(
                f"{name}(required={port.required})"
            )
    return unfillable


def test_the_sweep_has_something_to_scan():
    """Guard the guard (#4382): an empty registry would pass vacuously."""
    tool_defs = _tool_defs()
    assert len(tool_defs) >= 100, (
        f"only {len(tool_defs)} tools in the registry — the tool modules were "
        "not imported and this sweep is measuring nothing"
    )
    outputs = _output_port_ids()
    assert len(outputs) >= 40, (
        f"only {len(outputs)} distinct output port ids — port data is missing"
    )
    total_inputs = sum(len(td.input_ports) for td in tool_defs.values())
    assert total_inputs >= 100, (
        f"only {total_inputs} declared input ports found — nothing to check"
    )


def test_every_declared_input_port_is_fillable_by_some_tool_output():
    """A port nothing can fill is work the user asked for and never got."""
    unfillable = _unfillable_inputs()
    rendered = "\n  ".join(
        f"{pid!r} declared by {', '.join(tools)}"
        for pid, tools in sorted(unfillable.items())
    )
    assert unfillable == {}, (
        f"{len(unfillable)} declared input port(s) cannot be filled by ANY "
        "tool's declared output, and are not declared config-supplied. An "
        "edge to them is impossible, so the node runs with the port empty and "
        "silently does less than it claims — the #4404 shape:\n  " + rendered
    )


def test_allowlist_has_no_stale_entries():
    """Bidirectional hygiene: a config-supplied exception must stay true."""
    outputs = _output_port_ids()
    declared_inputs = {
        port.id for td in _tool_defs().values() for port in td.input_ports
    }

    now_fillable = sorted(p for p in CONFIG_SUPPLIED_PORTS if p in outputs)
    assert now_fillable == [], (
        "these ports are allowlisted as config-supplied but a tool now emits "
        f"them — they are real data-flow ports, drop the exception: {now_fillable}"
    )
    unknown = sorted(p for p in CONFIG_SUPPLIED_PORTS if p not in declared_inputs)
    assert unknown == [], (
        "these allowlist entries match no declared input port — the ports they "
        f"excused are gone: {unknown}"
    )
    missing_reason = sorted(
        p for p, reason in CONFIG_SUPPLIED_PORTS.items() if not str(reason).strip()
    )
    assert missing_reason == [], (
        f"allowlist entries without a reason: {missing_reason}"
    )


@pytest.mark.parametrize("tool_name", ["summarize_folder", "summarize_collection"])
def test_container_identity_ports_are_fillable(tool_name: str):
    """#4404 specifically: container identity must reach the tools that need it.

    Split out from the sweep so the archetype is addressable on its own and
    so a fix for it is visible as this test going green, independently of
    whatever else the broad sweep is reporting at the time.
    """
    tool_def = workflow_registry.get_tool_def(tool_name)
    assert tool_def is not None, f"{tool_name} is not registered"

    outputs = _output_port_ids()
    identity_ports = [
        port.id for port in tool_def.input_ports if port.id.endswith("_id")
    ]
    assert identity_ports, (
        f"{tool_name} declares no *_id input port — this test no longer "
        "describes the tool and must be updated"
    )
    unfillable = [pid for pid in identity_ports if pid not in outputs]
    assert unfillable == [], (
        f"{tool_name} needs {unfillable} but no source tool emits it, so the "
        "tool can never be told which container the user selected (#4404)"
    )
