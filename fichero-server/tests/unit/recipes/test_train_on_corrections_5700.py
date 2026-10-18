"""`source.train.on-the-persons-corrections` (#5700): the line reader's train offer fine-tunes on the lines a person
corrected (teacher `person`), the material its readiness counts; distilling a model's lines stays a second way.

WHY: the offer counted corrected lines ("Needs 2,000 corrected lines") but trained on a model's readings.
"""
from __future__ import annotations

from fichero_server.recipes.train_offers import due_starts, train_offers

RECIPE = {"steps": [{"id": "read", "job": "read-a-line", "settings": {}}]}
COUNTS = {"pages": [{"lines": 3000}] * 20, "unmarked": 0, "region_pages": 0, "scope_ids": ["root"], "teacher": None}
HERE = {"mode": "here", "why": ""}


def test_the_first_way_fine_tunes_on_the_persons_corrected_lines_5700():
    (offer,) = train_offers(RECIPE, COUNTS, stays_local=True, setting=HERE)
    first = offer["ways"][0]
    assert first["how"] == "fine-tune" and "corrected" in first["says"]
    assert first["targets"][0]["params"] == {"scope_ids": ["root"], "teacher": "person"}


def test_under_here_the_persons_lines_are_what_trains_even_with_no_model_teacher_5700():
    (offer,) = train_offers(RECIPE, COUNTS, stays_local=True, setting=HERE)
    assert due_starts([offer]) == [("training.start_here", {"scope_ids": ["root"], "teacher": "person"})]


def test_distilling_a_models_lines_is_still_offered_with_its_teacher_5700():
    (offer,) = train_offers(RECIPE, {**COUNTS, "teacher": "gemini-2.5-pro"}, stays_local=False, setting=HERE)
    distil = [w for w in offer["ways"] if w["how"] == "distil" and w["method"] == "kraken"]
    assert distil and distil[0]["targets"][0]["params"]["teacher"] == "gemini-2.5-pro"
