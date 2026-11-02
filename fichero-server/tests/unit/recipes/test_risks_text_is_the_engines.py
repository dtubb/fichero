"""`designer.how.risks-in-plain-words` (#6052): the block is the engine's topic text, served; the app has no copy."""
from __future__ import annotations

import pytest

from fichero_server.recipes import topics

pytestmark = pytest.mark.recipe_designer


def test_the_risks_block_is_a_topic_naming_insertion_and_the_chain():
    topic = topics.get_topic("how-risks")
    assert topic and topic.kind == "topic" and topic.title == "Reading the numbers"
    for words in ("deterministic", "invent", "insertion rate", "early error carries through the chain", "Check the earliest steps first"):
        assert words in topic.text


def test_the_topics_route_serves_it():
    from fastapi.testclient import TestClient

    from fichero_server.api.main import app

    body = TestClient(app).get("/api/topics").json()
    items = body["items"] if isinstance(body, dict) else body
    assert any(t["id"] == "how-risks" for t in items)
