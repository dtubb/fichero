"""#6254: setup offered no way to choose Kraken for Find lines. The engine lists Kraken's line finder for the step
(`/api/recipes/candidates`), but the plan's step menus (`step_choices`) left Find lines out (`CHOICE_JOBS`), so the
person saw no menu for it at all. Its menu lists Kraken whether or not anything is downloaded."""
from __future__ import annotations

from fichero_server.recipes.cards import seed_cards
from fichero_server.recipes.step_choices import step_choices

KRAKEN = "kraken:builtin/blla@bundled"


def test_find_lines_has_a_menu_that_offers_kraken():
    recipe = {"steps": [{"id": "lines", "job": "find-lines", "card": {"id": "apple:vision/find-lines@os"}}]}
    menus = step_choices(recipe, {}, list(seed_cards()), may_leave=False)
    lines = next((m for m in menus if m["job"] == "find-lines"), None)
    assert lines is not None, "Find lines has no menu on the plan"
    assert lines["name"] == "Find lines"
    assert KRAKEN in [c["card"] for c in lines["candidates"]]
