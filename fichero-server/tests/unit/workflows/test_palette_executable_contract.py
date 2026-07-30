"""Palette == executable contract (#4322).

The node-editor palette is fed by GET /api/workflows/tools (and /tools/grouped).
Historically 16 built-in defs had no implementation, so dragging one into a
workflow made the whole graph fatal at build ("Unknown tool"). The contract:
every tool the palette offers must resolve to a runnable implementation,
directly or through TOOL_ALIASES.
"""

import asyncio

from fichero_server.workflows.registry import (
    TOOL_ALIASES,
    get_tool,
    is_tool_executable,
    list_executable_tools,
    list_executable_tools_by_category,
    get_categories,
    list_tools,
)

# The known placeholder defs (#4322 out-of-scope backlog). If one of these
# gains an implementation it simply reappears in the palette — this set is
# only used to prove the filter actually removes known-dead entries.
KNOWN_UNIMPLEMENTED = {
    "crop",
    "custom_llm",
    "enhance",
    "export",
    "filter",
    "if",
    "loop",
    "merge",
    "rotate",
    "save_to_library",
    "segment",
    "switch",
    "to_excel",
    "to_json",
    "to_pdf",
    "to_word",
}


def test_every_palette_tool_is_executable():
    tools = list_executable_tools()
    assert tools, "palette must not be empty"
    for tool in tools:
        assert get_tool(tool.name) is not None, (
            f"palette offers '{tool.name}' but it has no implementation — "
            "it would be fatal at graph build"
        )


def test_known_placeholders_are_filtered_out():
    names = {t.name for t in list_executable_tools()}
    still_missing = {
        n for n in KNOWN_UNIMPLEMENTED if not is_tool_executable(n)
    }
    assert not (still_missing & names)


def test_aliased_tools_stay_in_palette():
    names = {t.name for t in list_executable_tools()}
    for alias in TOOL_ALIASES:
        if is_tool_executable(alias):
            assert alias in names, f"aliased tool '{alias}' must stay in the palette"
    assert "summarize" in names  # summarize → summarize_file


def test_grouped_palette_matches_flat_palette():
    flat = {t.name for t in list_executable_tools()}
    grouped: set[str] = set()
    for category in get_categories():
        grouped |= {t.name for t in list_executable_tools_by_category(category)}
    assert grouped == flat


def test_unfiltered_registry_keeps_placeholder_defs():
    # The registry itself is NOT stripped — validation and diagnostics can
    # still see placeholder defs; only the palette endpoints filter.
    all_names = {t.name for t in list_tools()}
    unimplemented = {n for n in KNOWN_UNIMPLEMENTED if not is_tool_executable(n)}
    assert unimplemented <= all_names


def test_tools_route_serves_only_executable_tools():
    from fichero_server.api.routes.workflow.workflows import list_workflow_tools

    response = asyncio.run(list_workflow_tools())
    assert response.count == len(response.items)
    for item in response.items:
        assert get_tool(item.name) is not None
