"""`mcp.client.tools-reach-a-workflow` (#5760): an MCP server's tools are in the workflow node palette with no hidden
flag. WHY (2026-10-17 review): the palette showed `mcp_*` tools only behind `workflowToolsMcp`, tier dev, so a person
who added a server (Settings › MCP) never saw its tools in a workflow. The flag is alpha, which is on by default
for the app's own builds like the Settings tab (`mcpUi`) that adds the servers."""
from __future__ import annotations


def test_the_mcp_palette_flag_is_as_visible_as_the_mcp_settings_tab():
    from fichero_server.api.feature_tiers_generated import FEATURE_TIERS

    assert FEATURE_TIERS["workflowToolsMcp"] == FEATURE_TIERS["mcpUi"] == "alpha"
