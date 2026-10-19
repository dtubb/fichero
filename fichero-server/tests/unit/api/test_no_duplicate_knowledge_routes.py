"""`research.mcp-knowledge-endpoints-unwired` (#1439): the eight `/api/mcp/tools/knowledge/*` routes duplicated
`/api/entities` and `/api/claims`, so one capability surfaced as two MCP tools (toolset `mcp`). They are retired;
`POST /api/mcp/tools/check/verdicts` stays (it carries `source.check.model-never-a-person`). Read from the contract the
clients are generated from."""
from __future__ import annotations

import json
from pathlib import Path

CONTRACT = Path(__file__).resolve().parents[2] / "contracts" / "openapi.json"


def test_no_route_duplicates_the_entities_and_claims_routes():
    paths = set(json.loads(CONTRACT.read_text())["paths"])
    assert not [p for p in paths if p.startswith("/api/mcp/tools/knowledge")], "a duplicate knowledge route is back"
    assert "/api/mcp/tools/check/verdicts" in paths
