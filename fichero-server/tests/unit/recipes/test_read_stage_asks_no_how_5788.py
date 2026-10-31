"""Onboarding ruling 2026-10-18 (#5788): the Read stage no longer asks "line by line or the page at once?".

WHY: lines are the default and the owner dropped the question; what is left on Read is the second model, and (variant A,
#5894) which lines it gets: the certainty bar, read by the correct step.
"""

from __future__ import annotations

from fichero_server.recipes.stages import STAGES


def test_read_asks_whether_a_second_model_checks_the_reading_and_which_lines_it_gets():
    read = next(s for s in STAGES if s.id == "read")
    assert [q.key for q in read.questions] == ["correct_with_a_second_model", "correct_with_another_model", "second_review_mode",
                                                "review_certainty_bar"]
    assert not any("line" in q.key and "page" in q.key for q in read.questions)  # the line-or-page question stays dropped
