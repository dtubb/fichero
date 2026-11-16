"""`workflows.text-reflow.ai-refinement-works` (docs/contributor_manual/specs/ui/workflows.md, Step 1.5, #5921): the option is
REMOVED (owner ruling 2026-11-02). It called a function that never existed, so it never did anything.

WHY: an option that is on either works or says why; this one did neither. A workflow stored with it still opens, saves and
runs: the key is ignored, with no error.
"""

from __future__ import annotations

import asyncio

from fichero_server.llm import LLMConfig
from fichero_server.workflows import registry
from fichero_server.workflows.tools import text_reflow


def test_the_tool_offers_no_option_and_no_model():
    tool = registry.get_tool_def("text_reflow")
    assert tool is not None
    assert not tool.config_schema and tool.uses_llm is False
    assert "AI refinement" not in tool.description


def test_the_dead_refinement_path_is_gone():
    for name in ("_refine_with_llm", "_say_refinement_unavailable", "REFINEMENT_UNAVAILABLE", "_REFLOW_AI_INSTRUCTIONS"):
        assert not hasattr(text_reflow, name), name


def test_a_stored_workflow_that_still_names_the_option_is_accepted_and_ignored():
    config = LLMConfig(provider="openai", model="gpt-x")
    text = "First line of a para-\ngraph that wraps\nacross lines."
    plain = asyncio.run(text_reflow.text_reflow({"text": text}, {}, config))
    named = asyncio.run(text_reflow.text_reflow({"text": text, "_config": {"use_ai_refinement": True}}, {}, config))
    assert named == plain and "paragraph" in plain["text"]


def test_a_workflow_saved_with_the_old_key_saves_without_error(client):
    node = {"id": "r", "tool": "text_reflow", "label": "Reflow", "config": {"use_ai_refinement": True}}
    made = client.post("/api/workflows", json={"name": "old reflow", "edges": [], "nodes": [node]})
    assert made.status_code == 200, made.text
