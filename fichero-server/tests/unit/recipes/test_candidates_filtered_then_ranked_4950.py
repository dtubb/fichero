"""`source.recipe.candidates-filtered-then-ranked` (#4950): candidates are kept only if they pass the hard constraints,
then ranked in a fixed order: accuracy in one-point bands first, then local before remote, cheaper, and the card id
last so a tie is always broken the same way (`assemble._choose`, `_rank_key`).
"""
from __future__ import annotations

from dataclasses import replace

from fichero_server.recipes.assemble import Answers, Card, _choose

SPANISH = Answers(purposes=("transcribe",), languages=frozenset({"es"}), scripts=frozenset({"Latn"}),
                  materials=("handwriting",), material="handwriting", cloud_allowed=True)
BASE = Card(id="b", pin={"hf": "x/b"}, jobs=frozenset({"read-a-line"}), scripts=frozenset({"Latn"}),
            languages=frozenset({"es"}), material=frozenset({"handwriting"}), cer_published=0.10)


def _best(*cards):
    return _choose("read-a-line", list(cards), SPANISH).card.id


def test_a_card_that_fails_a_hard_constraint_is_never_kept_however_accurate():
    greek = replace(BASE, id="greek", scripts=frozenset({"Grek"}), cer_published=0.01)
    assert _best(greek, BASE) == "b"


def test_a_better_accuracy_band_wins_over_local_and_cheap():
    cloud = replace(BASE, id="cloud", runs_on="cloud:openai", cost_per_page=0.01, cer_published=0.04)
    assert _best(BASE, cloud) == "cloud"


def test_inside_one_band_local_comes_before_remote_and_cheaper_before_dearer():
    cloud = replace(BASE, id="a-cloud", runs_on="cloud:openai", cer_published=0.105)
    assert _best(cloud, BASE) == "b"  # same one-point band: this Mac first, whatever the id
    dear = replace(BASE, id="a-dear", runs_on="cloud:openai", cost_per_page=0.02, cer_published=0.10)
    cheap = replace(BASE, id="z-cheap", runs_on="cloud:openai", cost_per_page=0.01, cer_published=0.10)
    assert _best(dear, cheap) == "z-cheap"


def test_a_tie_is_broken_by_the_card_id():
    assert _best(replace(BASE, id="m"), replace(BASE, id="c")) == "c"
