"""#6122: the Search stage's page says what is embedded (the owner could not tell pages, groups of pages or segments)."""
from __future__ import annotations

from fichero_server.recipes.stages import STAGES


def test_the_search_stage_says_what_it_embeds_and_that_one_model_serves_the_project():
    search = next(s for s in STAGES if s.id == "search")
    words = search.sentence
    assert "each page's text" in words and "claims and entities" in words and "one search model" in words
