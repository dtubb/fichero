"""`source.onboard.train-path` (spec review 2026-10-20) and `source.try.every-job`: Set Up says early how many corrected
lines training a model of your own will need, in ONE sentence per trainable step (not the greyed rows #5804 removed),
and says plainly which stages can be tried on the sample pages and which cannot yet."""
from __future__ import annotations

from fichero_server.recipes.stages import STAGES, listing
from fichero_server.recipes.train_offers import offered, train_ahead, train_offers

RECIPE = {"steps": [{"id": "regions", "job": "find-regions"}, {"id": "read", "job": "read-a-line"},
                    {"id": "names", "job": "find-names-tag-words"}]}
NONE = {"pages": [], "unmarked": 0, "region_pages": 0}


def _ready():
    page = {"id": "p", "lines": 1200, "name": "p"}
    return {"pages": [page, {**page, "id": "q"}], "unmarked": 0, "region_pages": 2, "teacher": "kraken",
            "scope_ids": ["root"]}


def test_below_the_threshold_a_sentence_says_how_many_lines_training_needs_and_there_is_still_no_offer():
    offers = train_offers(RECIPE, NONE, stays_local=False)
    assert offered(offers) == []  # #5804 stands: no greyed row
    ahead = {a["step"]: a for a in train_ahead(offers)}
    assert set(ahead) == {"regions", "read"}  # the names step has no trainer: nothing to ask for
    sentence = ahead["read"]["sentence"]
    assert "2,000" in sentence and "corrected lines" in sentence and "0 on 0 pages" in sentence
    assert sentence.startswith("Training a model of your own") and sentence.endswith(".")


def test_once_there_is_enough_the_sentence_gives_way_to_the_offer():
    offers = train_offers(RECIPE, _ready(), stays_local=False)
    assert train_ahead(offers) == [] and offered(offers)


def test_the_plan_carries_it(client, with_material):
    plan = client.get("/api/recipes/project/start")
    assert plan.status_code in (200, 422)  # no recipe saved yet is refused in words, not a field missing
    assert "train_ahead" in (client.get("/openapi.json").json()["components"]["schemas"]["StartPlan"]["properties"])


def test_every_stage_says_whether_it_can_be_tried_and_one_that_cannot_says_so_in_words():
    for stage in listing(None):
        if stage["sampleable"]:
            assert stage["not_tried"] is None, stage["id"]
        else:
            assert stage["not_tried"] and stage["not_tried"].endswith(".") and stage["title"] not in stage["not_tried"], stage["id"]
    assert {s["id"] for s in listing(None)} <= {s.id for s in STAGES}
