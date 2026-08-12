"""Tool parallelism classification (pipelining lane step 1, 2026-08-12).

`ToolDef.parallelism` states how a tool relates to the item stream:
elementwise tools map one item at a time and may be Send-chained so pages
STREAM through consecutive nodes; reducing tools need the whole set and
demand an aggregation barrier; "batch" is the unclassified default that
keeps today's aggregate-then-call shape. The builder's streaming work
builds on exactly this pin — a tool that changes class changes run
semantics, so the classification is a contract, not a hint.
"""

import fichero_server.workflows.tools  # noqa: F401 — populate the registry
from fichero_server.workflows.registry import get_tool_def, list_tools

ELEMENTWISE = {
    "transcribe",
    "describe",
    "summarize_file",
    "extract_entities",
    "detect_regions",
    "caption",
    "classify",
    "classify_script",
}

REDUCING = {"merge_dedup_only", "kg_persist_finalize", "aggregate"}


class TestParallelismContract:
    def test_elementwise_tools_are_classified(self):
        for name in ELEMENTWISE:
            tool = get_tool_def(name)
            assert tool is not None, f"{name} not registered"
            assert tool.parallelism == "elementwise", (
                f"{name}: expected elementwise, got {tool.parallelism}"
            )

    def test_reducing_tools_are_classified(self):
        for name in REDUCING:
            tool = get_tool_def(name)
            assert tool is not None, f"{name} not registered"
            assert tool.parallelism == "reducing", (
                f"{name}: expected reducing, got {tool.parallelism}"
            )

    def test_everything_else_defaults_to_batch(self):
        classified = ELEMENTWISE | REDUCING
        for tool in list_tools():
            if tool.name.startswith("_") or tool.name in classified:
                continue
            assert tool.parallelism == "batch", (
                f"{tool.name} is classified {tool.parallelism!r} but not in the "
                "pinned sets — classify it HERE too; the class changes run "
                "semantics."
            )

    def test_only_valid_values(self):
        for tool in list_tools():
            assert tool.parallelism in {"elementwise", "reducing", "batch"}
