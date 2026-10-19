"""#5804 (`source.recipe.train-offered-once-ready`): training is offered only once there is enough corrected work.

WHY: a new project has no corrected lines, so Set Up listed every row greyed ("Needs 2,000 corrected lines... 0 on 0"),
twice for one way, with a lowercase machine reason, and a spaCy trainer Fichero does not have.
"""
from __future__ import annotations

from fichero_server.recipes.train_offers import offered, train_offers

RECIPE = {"steps": [
    {"id": "regions", "job": "find-regions"}, {"id": "read", "job": "read-a-line"},
    {"id": "names", "job": "find-names-tag-words"},
]}
NONE = {"pages": [], "unmarked": 0, "region_pages": 0}


def _ready_counts():
    page = {"id": "p", "lines": 1200, "name": "p"}
    return {"pages": [page, {**page, "id": "q"}], "unmarked": 0, "region_pages": 2,
            "teacher": "kraken", "scope_ids": ["root"]}


def test_below_the_threshold_there_is_no_offer_at_all():
    assert offered(train_offers(RECIPE, NONE, stays_local=False)) == []


def test_a_trainer_fichero_does_not_have_is_left_out_entirely():
    offers = offered(train_offers(RECIPE, _ready_counts(), stays_local=False))
    assert "names" not in [o["step"] for o in offers]
    assert all(w["targets"] or w["why"] for o in offers for w in o["ways"])
    assert not [w for o in offers for w in o["ways"] if "no spaCy" in (w["why"] or "")]


def test_each_way_is_listed_once():
    for offer in offered(train_offers(RECIPE, _ready_counts(), stays_local=False)):
        keys = [(w["method"], w["how"]) for w in offer["ways"]]
        assert len(keys) == len(set(keys))


def test_a_refused_way_says_what_to_do_in_a_sentence():
    offers = offered(train_offers(RECIPE, _ready_counts(), stays_local=True))
    refused = [w for o in offers for w in o["ways"] if not w["available"]]
    assert refused, "pages kept on this Mac refuse the Hugging Face-only way"
    for way in refused:
        why = way["why"]
        assert why[0].isupper() and why.endswith(".") and "Allow" in why and "or choose" in why
