"""`openapi.mcp.refusals-in-words` (docs/contributor_manual/specs/harness/surfaces-from-openapi.md).

WHY (2026-10-11, a hands-on pass calling every read-only MCP tool on a scratch project): a refusal is all an agent
has to go on, and some said what only the engine's own code knows: a route to call ("POST
/kg/claim-search/embed first"), an internal record's class name ("No SourceMetadata found"), or a target the caller
never named ("Document not found: library"). Each says what is missing, in words, and what to do.
"""
from __future__ import annotations

import re

_INTERNALS = re.compile(r"(GET|POST|PUT|PATCH|DELETE) /|/api/|/kg/|SourceMetadata")


def _said(response) -> str:
    detail = response.json().get("detail")
    return detail if isinstance(detail, str) else str(detail)


def test_meaning_search_before_anything_is_indexed_says_so_in_words(client):
    for route in ("/api/kg/claim-search", "/api/kg/entity-curation/semantic"):
        r = client.get(route, params={"q": "testigo"})
        assert r.status_code == 503, (route, r.text)
        said = _said(r)
        assert not _INTERNALS.search(said), (route, said)
        assert "index" in said.lower(), (route, said)


def test_effective_rights_of_a_document_not_named_asks_for_it(client):
    r = client.get("/api/rights/effective", params={"target_kind": "document"})
    assert r.status_code == 422, r.text
    said = _said(r)
    assert "library" not in said.lower() or "target_id" in said, said
    assert "target_id" in said and "document" in said, said
