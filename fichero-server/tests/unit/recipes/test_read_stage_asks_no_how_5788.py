"""Onboarding ruling 2026-10-18 (#5788): the Read stage no longer asks "line by line or the page at once?".

WHY: lines are the default and the owner dropped the question; the one question left on Read is the second model.
"""

from __future__ import annotations

from fichero_server.recipes.stages import STAGES


def test_read_asks_only_whether_a_second_model_checks_the_reading():
    read = next(s for s in STAGES if s.id == "read")
    assert [q.key for q in read.questions] == ["correct_with_a_second_model"]
