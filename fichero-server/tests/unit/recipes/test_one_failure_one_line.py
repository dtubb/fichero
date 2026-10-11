"""`source.recipe.batch-at-archive-scale`: one failure, one line.

Seen 2026-10-11 on a first-run onboarding: the run's row repeated one download failure once per step, about eight
copies of "step X not run on 1 of 0 folders (pages in no folder: its model … did not download: …)". A run's failure
summary says each cause once, with the steps it stopped ("2 steps (correct; translate) did not run: why"), and
never counts "1 of 0 folders": with no folders counted it names no count.
"""

from __future__ import annotations

from fichero_server.recipes.runner import _failures_words

WHY = "its model Qwen2.5-VL 7B (OCR) did not download: the local model runtime could not be set up"


class _NoDocs:
    def get(self, _model, _id):
        return None


def _card(name: str) -> dict:
    return {"steps": [name], "card": "workflow"}


def _not_run(folder=None, why=WHY) -> dict:
    return {"state": "not run", "failed_batches": [{"folder": folder, "state": "not run", "child_id": None, "why": why}]}


def test_the_same_cause_over_many_steps_is_said_once():
    cards = [_card("correct")] + [_card("translate-transliterate-normalise")] * 4
    steps = [_not_run() for _ in cards]

    words = _failures_words(_NoDocs(), cards, steps, total=0)

    assert words.count(WHY) == 1, words
    assert words == f"2 steps (correct; translate-transliterate-normalise) did not run: {WHY}", words


def test_no_folders_counted_names_no_count():
    words = _failures_words(_NoDocs(), [_card("correct")], [_not_run()], total=0)
    assert "of 0" not in words and words == f"step correct did not run: {WHY}", words


def test_different_causes_are_each_said_once():
    cards = [_card("lines, read"), _card("names")]
    steps = [{"state": "failed", "failed_batches": [{"folder": None, "state": "failed", "child_id": None,
                                                     "why": "1 page failed"}]},
             _not_run(why="it needs lines, which no earlier step gave")]

    words = _failures_words(_NoDocs(), cards, steps, total=1)

    assert words == ("step lines, read failed on 1 of 1 folder (pages in no folder: 1 page failed); "
                     "step names did not run on 1 of 1 folder (pages in no folder: it needs lines, which no earlier "
                     "step gave)"), words
