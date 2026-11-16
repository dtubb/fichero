"""`designer.defaults.says-why` (#6052): every default carries its row's why and what chose it; a default with no row says the usual."""
from __future__ import annotations

import pytest

from fichero_server.recipes import defaults

pytestmark = pytest.mark.recipe_designer


def test_a_default_says_its_row_and_what_chose_it():
    got = defaults.resolve({"materials": ["handwriting"], "condition": ["faded"], "how": {"places": ["this-mac"], "matters": "privacy"}})
    line = defaults.says_why(got, "prepare")
    assert "faded ink reads better after contrast" in line and "chosen because: faded" in line
    assert "nothing leaves this Mac" in defaults.says_why(got, "steps") and "handwriting, privacy, this mac" in defaults.says_why(got, "steps")


def test_a_default_with_no_row_says_the_usual():
    got = defaults.resolve({})
    assert defaults.says_why(got, "model_kind") == defaults.USUAL
    assert defaults.says_why(got, "no-such-key") == defaults.USUAL
