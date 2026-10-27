"""The stage-3 similar-name score reads the NEW name against each stored one, in that order (reviews 2026-10-27).

WHY: `SequenceMatcher.ratio()` is not symmetric. #6236's speed-up kept one matcher for the needle as its second
sequence, which turned the comparison around: about a quarter of name pairs near the 0.78 floor crossed it in one
order only, and the similar-name proposals changed. The answers below are origin/integration's, before the speed-up.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from fichero_server.workflows.tools._entity_writer import _fuzzy_match_existing


@pytest.mark.parametrize(("new_name", "stored_name", "proposed"), [
    ("Juan Rosas Mesa", "Juan Lara Mesa", True),  # ratio 0.828 this way round, 0.759 the other
    ("Juan Lara Mesa", "Juan Rosas Mesa", False),
    ("Piopoayan", "Popayan", True),
    ("Popayan", "Piopoayan", False),
    ("Antonio Narino", "Oaktzio Narino", True),
    ("Oaktzio Narino", "Antonio Narino", False),
])
def test_a_new_name_is_scored_against_a_stored_one_in_the_order_it_always_was(new_name, stored_name, proposed):
    stored = SimpleNamespace(id="e1", canonical_name=stored_name, merged_into_id=None)
    assert (_fuzzy_match_existing([stored], new_name) is stored) is proposed
