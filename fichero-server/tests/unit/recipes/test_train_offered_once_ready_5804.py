"""#5804 (`source.recipe.train-offered-once-ready`): training is offered only once there is enough corrected work.

WHY: a new project has no corrected lines, so Set Up listed every row greyed ("Needs 2,000 corrected lines... 0 on 0"),
twice for one way, with a lowercase machine reason, and a spaCy trainer Fichero does not have.
"""
from __future__ import annotations

import pytest

from fichero_server.recipes.train_offers import offered, train_offers
from tests.unit.recipes.test_bakeoff_readers import _set_up, folder  # noqa: F401

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


@pytest.mark.parametrize("cloud_allowed", [True, False])
@pytest.mark.parametrize("app_places", [None, [], ["huggingface"], ["cloud"]])
def test_the_plan_and_auto_start_agree_on_the_place(client, db, tmp_path, folder, monkeypatch, cloud_allowed, app_places):  # noqa: F811
    """#5841: one place check for training (Hugging Face Jobs) in the Start plan and in auto-start, for each setting."""
    from fichero_server.recipes import places, train_offers as mod
    from fichero_server.recipes.train_offers import _offers_now

    _set_up(client)
    saved = client.get("/api/recipes/project").json()
    client.put("/api/recipes/project", json={"answers": {**saved["answers"], "cloud_allowed": cloud_allowed},
                                             "recipe": saved["recipe"]})
    if app_places is not None:
        places.set_places(app_places)
    monkeypatch.setattr(mod, "counted", lambda _db: _ready_counts())

    def shown(offers):
        read = next(o for o in offers if o["job"] == "read-a-line")
        return {(w["method"], w["how"], w["available"], w["why"]) for w in read["ways"]}

    planned = client.get("/api/recipes/project/start").json()["train_offers"]
    assert shown(planned) == shown(offered(_offers_now(db)))


def test_the_refusal_names_who_said_no(app_db):
    """#5841: the app's places forbid Hugging Face -> point at Set Up Fichero; the project said no -> at the project."""
    from fichero_server.recipes import places
    from fichero_server.recipes.train_offers import training_stays_local

    stays, why = training_stays_local({"cloud_allowed": True})
    assert not stays and why is None, "nothing answered yet caps nothing"
    places.set_places([])
    stays, why = training_stays_local({"cloud_allowed": True})
    assert stays and "Set Up Fichero" in why
    places.set_places(["huggingface"])
    stays, why = training_stays_local({"cloud_allowed": False})
    assert stays and "this project's pages" in why and "Set Up Fichero" not in why
