"""#5836 (`source.onboard.material.which-hand`): only real hands are ever offered.

WHY: the owner's 20th-century Latin test showed "Typewriter" and "20th century handwritten script" under Which hand. No code
offers them: they were saved answers (typed, or saved through the API) shown ticked. What the engine offers is its curated list.
"""
from __future__ import annotations

import pytest

from fichero_server.recipes.hands import HANDS, hands_for

NOT_HANDS = ("typewriter", "typescript", "print", "handwritten", "handwriting", "script", "century")


def test_no_curated_hand_is_a_typeface_or_a_placeholder():
    for hand in HANDS:
        title = hand.title.lower()
        assert not any(word in title for word in NOT_HANDS), hand.title
        assert hand.looks and hand.tags, f"{hand.title} says what it looks like and carries tags"


@pytest.mark.parametrize("script,period", [("Latn", "20th century"), ("Latn", "1950"), ("Latn", "16th century"),
                                           ("Arab", "19th century"), ("Hebr", None)])
def test_what_is_offered_is_only_ever_the_curated_list(script, period):
    ids = {h.id for h in HANDS}
    assert {h.id for h in hands_for(script, period)} <= ids


def test_a_typed_answer_is_never_among_the_offered_hands(client):
    saved = client.get("/api/recipes/project").json()
    answers = {**(saved["answers"] or {}), "hands": ["Typewriter", "20th century handwritten script"], "period": "20th century"}
    assert client.put("/api/recipes/project", json={"answers": answers, "recipe": saved["recipe"]}).status_code == 200
    offered = client.get("/api/recipes/hands", params={"script": "Latn", "period": "20th century"}).json()["items"]
    assert not [h for h in offered if h["title"].lower() in ("typewriter", "20th century handwritten script")]


def test_a_spanish_20th_century_latin_project_is_not_offered_only_kurrent_6118():
    """#6118: the owner's Spanish, Latin, 20th-century project listed Kurrent (German cursive) as its only hand."""
    ids = [h.id for h in hands_for("Latn", "20th century", ["es"])]
    assert "kurrent" not in ids
    assert {"palmer", "modern-cursive"} <= set(ids)


def test_a_hand_from_another_tradition_is_never_the_only_one_shown_6118():
    for period in ("20th century", "1950", "19th century"):
        for languages in (None, [], ["es"], ["en"], ["de"]):
            ids = [h.id for h in hands_for("Latn", period, languages)]
            assert ids, (period, languages)
            if languages and not set(languages) & {"de"}:
                assert ids != ["kurrent"], (period, languages)
