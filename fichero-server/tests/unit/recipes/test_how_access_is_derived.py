"""`designer.how.access-derived-and-confirmed` (#6052): what you have is shown from the derived facts, never stored."""
from __future__ import annotations

import pytest

from fichero_server.recipes import derived, how

pytestmark = pytest.mark.recipe_designer


def test_what_you_have_is_the_derived_facts_and_nothing_is_written_to_the_answers():
    assert {"chip", "memory_gb", "from"} <= set(derived.this_mac())  # the line the page shows (`GET /api/recipes/derived`)
    assert "access" not in how.normalise({"places": ["this-mac"]})[0]
