"""`source.model.page-text-is-constructed-from-the-segments` (#5486, #5467, ruled 2026-10-17).

Spec: docs/contributor_manual/specs/source/models-chains-and-projects.md. WHY: the Paleographer Review wrote the page's
text as a blob of its own, so a round that could not be tied to the lines still overwrote the page text with the
review's words, and the text no longer matched the lines it stands on. The page's text is the chosen reading,
constructed from its segments; a step writes readings onto lines, never the text. Driven through the real review tool on
the 5654 page (Kraken's three lines), the model stubbed.
"""
from __future__ import annotations

import pytest

from tests.unit.workflows.test_review_corrects_the_lines_5654 import (  # noqa: F401  (fixtures and helpers)
    KRAKEN_READS, _counting, _page_text, _review, page,
)


@pytest.mark.asyncio
async def test_a_review_that_cannot_be_tied_leaves_the_page_text_as_the_chosen_reading(page, monkeypatch):
    """source.model.page-text-is-constructed-from-the-segments: "where a correction cannot be tied to the lines ... the
    page's text stays what the chosen reading was"."""
    before_derived, before_cached = _page_text(page)

    await _review(page, monkeypatch, "el dicho escrivano vezino de la ciudad\ny lo firmo")

    derived, cached = _page_text(page)
    assert _counting(page) == KRAKEN_READS
    assert derived == before_derived and cached == before_cached, "the review's words became the page's text"


def test_the_correcting_step_does_not_write_the_page_text_by_default():
    """source.model.page-text-is-constructed-from-the-segments: "A step that reads or corrects a page writes readings
    onto the page's lines; it does not write the page's text"."""
    from fichero_server.workflows.registry import TOOL_DEFS

    import fichero_server.workflows.tools.transcribe_review  # noqa: F401  (registers the tool)

    assert TOOL_DEFS["transcribe_review"].config_defaults["update_page_content"] is False


def test_no_shipped_review_node_writes_the_page_text():
    """source.model.page-text-is-constructed-from-the-segments: the shipped workflows' correcting nodes (the recipe's
    `correct` job runs Paleographer Review's r3) write readings onto lines, never the page text; the tool's default alone
    does not decide it when a preset sets the option itself."""
    import json

    from fichero_server.workflows.default_workflows import _PRESETS_DIR

    wrote = []
    for path in sorted(_PRESETS_DIR.glob("*.json")):
        for node in json.loads(path.read_text(encoding="utf-8")).get("nodes", []):
            if node.get("tool") == "transcribe_review" and (node.get("config") or {}).get("update_page_content", False):
                wrote.append(f"{path.name}:{node['id']}")
    assert wrote == [], wrote
