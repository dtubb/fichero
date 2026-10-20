"""Training belongs in the recipe (#5660 item 9, `source.recipe.train-offered-per-step`), tested to the spec.

For each step a model can be trained for, the Start plan offers "Train a model of your own for this step" (was "on your corrected pages": the
ways (fine-tune or distil), each with the places the engine trains on today and the audited action that starts
it there; a way with no trainer is listed as not available yet. It is offered later, never run at Start, and
says how many more corrected lines and pages it needs, counted as the bake-off counts them.
"""
from __future__ import annotations

from fichero_server.recipes.assemble import TRAIN_OFFERED_FROM_LINES
from fichero_server.recipes.bakeoff import MIN_PAGES
from fichero_server.recipes.train_offers import TITLE, counted, train_offers
from tests.unit.recipes.test_bakeoff_readers import LINES_PER_PAGE, _corrected, _set_up, folder  # noqa: F401
from tests.unit.training.test_yolo_regions_training import _page, _persons_regions

RECIPE = {"steps": [
    {"id": "regions", "job": "find-regions"}, {"id": "lines", "job": "find-lines"},
    {"id": "read", "job": "read-a-line"}, {"id": "names", "job": "find-names-tag-words"},
    {"id": "dates", "job": "work-out-dates"},
]}
NONE = {"pages": [], "unmarked": 0, "region_pages": 0}


def _ways(offer):
    return {w["method"]: w for w in offer["ways"]}


def test_each_trainable_step_is_offered_its_ways_and_where_they_run():
    """WHY: training is offered per step, with only the trainers and places the engine has: a way offered
    with a place it cannot run on, or a trainer that does not exist, would be a button that fails."""
    offers = train_offers(RECIPE, NONE, stays_local=False)
    assert [(o["step"], o["job"], o["title"]) for o in offers] == [
        ("regions", "find-regions", TITLE), ("read", "read-a-line", TITLE), ("names", "find-names-tag-words", TITLE)]
    regions, read, names = (_ways(o) for o in offers)

    assert read["kraken"]["how"] == "distil" and read["mlx-vision-lora"]["how"] == "distil"  # both learn from a teacher
    assert [(t["place"], t["starts"]) for t in read["kraken"]["targets"]] == [
        ("this-mac", "training.start_here"), ("huggingface-jobs", "training.start")]
    assert [(t["place"], t["starts"]) for t in read["mlx-vision-lora"]["targets"]] == [
        ("huggingface-jobs", "training.start_vision_lora")]
    assert [(t["place"], t["starts"]) for t in regions["yolo"]["targets"]] == [
        ("this-mac", "training.start_regions_here")]
    # No spaCy trainer in the engine: listed, never offered as if it ran.
    assert names["spacy-ner"]["available"] is False and "not available yet" in names["spacy-ner"]["why"]
    assert names["spacy-ner"]["targets"] == []
    # And so it asks for no count of corrections that nothing here would read (#5659 hands-on pass).
    assert offers[2]["readiness"] == {"ready": False, "sentence": None}
    places = {t["place"] for o in offers for w in o["ways"] for t in w["targets"]}
    assert places <= {"this-mac", "huggingface-jobs"}


def test_a_project_that_keeps_its_pages_here_is_offered_only_this_mac():
    """`source.project.stays-local`: pages never leave the Mac, so Hugging Face Jobs is not offered, and a way
    that runs only there says why it is not available."""
    (_, read, _) = (_ways(o) for o in train_offers(RECIPE, NONE, stays_local=True))
    assert [t["place"] for t in read["kraken"]["targets"]] == ["this-mac"]
    assert read["mlx-vision-lora"]["available"] is False and "Your pages stay on this Mac" in read["mlx-vision-lora"]["why"]


def test_it_says_how_many_more_corrected_lines_and_pages_it_needs():
    """WHY: the offer waits for enough corrections; it must say how many more, as the bake-off says it, at the
    train step's own threshold when the recipe has one."""
    pages = [{"document_id": "p1", "name": "p1", "lines": 44}]
    read = train_offers(RECIPE, {**NONE, "pages": pages}, stays_local=True)[1]["readiness"]
    assert (read["ready"], read["lines"], read["more_lines"], read["more_pages"], read["min_lines"]) == (
        False, 44, TRAIN_OFFERED_FROM_LINES - 44, MIN_PAGES - 1, TRAIN_OFFERED_FROM_LINES)
    assert read["sentence"].startswith("Needs 2,000 corrected lines on at least 2 pages; this project has 44 on 1 page.")
    assert "Correct 1,956 more lines, on at least 1 more page." in read["sentence"]

    with_train = {"steps": RECIPE["steps"] + [{"id": "train", "job": "train-a-model", "settings": {"base": "read"},
                                               "offered_when": {"corrected_lines_at_least": 50}}]}
    pages2 = pages + [{"document_id": "p2", "name": "p2", "lines": 10}]
    ready = train_offers(with_train, {**NONE, "pages": pages2}, stays_local=True)[1]["readiness"]
    assert ready["ready"] and ready["sentence"] is None and ready["min_lines"] == 50

    regions = train_offers(RECIPE, {**NONE, "region_pages": 1}, stays_local=True)[0]["readiness"]
    assert (regions["ready"], regions["more_pages"]) == (False, 1)
    assert regions["sentence"].endswith("Draw or correct the regions on 1 more page.")


def test_the_start_plan_carries_the_offers_counted_on_the_project(client, db, tmp_path, folder, with_material):  # noqa: F811
    """Through the route: the offers are on the Start plan, counted on the project's corrected pages and a
    person's regions, and never among what Start runs (`source.recipe.train-never-automatic`)."""
    _set_up(client)
    _corrected(db, tmp_path, "SM_NPQ_C01_001", folder)
    page = _page(db, tmp_path, "regions-1", folder)
    _persons_regions(client, page, [("text-block", [0.2, 0.1, 0.7, 0.8])])
    assert counted(db)["region_pages"] == 1

    plan = client.get("/api/recipes/project/start")
    assert plan.status_code == 200, plan.text
    body = plan.json()
    assert body["train_offers"] == [], "below the threshold the plan shows no offer (#5804)"
    from fichero_server.recipes.train_offers import _offers_now

    read = next(o for o in _offers_now(db) if o["job"] == "read-a-line")
    assert read["readiness"]["lines"] == LINES_PER_PAGE and read["readiness"]["more_pages"] == 1
    assert read["readiness"]["more_lines"] == TRAIN_OFFERED_FROM_LINES - LINES_PER_PAGE
    assert all(r.get("job") != "train-a-model" for r in body["runs"])


def test_each_way_carries_what_its_action_needs_and_none_without_a_teacher():
    """The app posts `starts` with `params` as-is: the engine fills the scope and, for a distillation, the teacher
    (the reader that read most pages); with no reading yet, a taught way has no params."""
    from fichero_server.recipes.train_offers import _ways

    counts = {"teacher": "kraken-zenodo-21788410", "scope_ids": ["box-1"]}
    kraken = next(w for w in _ways("read-a-line", stays_local=False, counts=counts)
                  if w["method"] == "kraken" and w["how"] == "distil")
    here = next(t for t in kraken["targets"] if t["starts"] == "training.start_here")
    assert here["params"] == {"scope_ids": ["box-1"], "teacher": "kraken-zenodo-21788410"}
    regions = _ways("find-regions", stays_local=True, counts=counts)[0]["targets"][0]
    assert regions["params"] == {"name": "regions", "scope_ids": ["box-1"]}
    untaught = _ways("read-a-line", stays_local=True, counts={"teacher": None, "scope_ids": ["box-1"]})
    # a distillation needs a model's readings; the person's fine-tune (#5700) needs only their corrected lines
    assert all(t["params"] is None for w in untaught if w["how"] == "distil" for t in w["targets"])
    assert all(t["params"]["teacher"] == "person" for w in untaught if w["how"] == "fine-tune" for t in w["targets"])
