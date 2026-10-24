"""Set Up stage questions that name kinds are open-ended (#5805;
docs/contributor_manual/specs/source/models-chains-and-projects.md, `source.onboard.stages.kinds-are-open-ended` and
`passages-says-what-it-does`).

WHY: the staged build showed Statements and Passages with a FIXED list of kinds (Sales, Gifts…), which the spec had only
as examples. Every such question is now: every kind by default, the person can type their own, and suggestions come
only from what a sample try found."""
from __future__ import annotations

import pytest

from fichero_server.recipes.stages import listing

RECIPE = {"fichero_recipe": 1, "id": "t", "version": "0.1.0", "title": "t"}
#: The stage questions that name kinds (stage id, answer key).
OPEN = [("names", "entity_kinds"), ("statements", "statement_kinds"), ("dates", "calendars"),
        ("structured-data", "fields")]  # Passages waits for its job and is not listed (`source.job.pull-out-passages`)


def _question(items, stage, key):
    return next(q for s in items if s["id"] == stage for q in s["questions"] if q["key"] == key)


@pytest.mark.parametrize(("stage", "key"), OPEN)
def test_every_kinds_question_is_open_with_every_kind_by_default(stage, key):
    q = _question(listing(None), stage, key)
    assert q["open_ended"] is True
    if (stage, key) == ("names", "entity_kinds"):  # tick boxes, all ticked, own kinds still typed
        assert [o["id"] for o in q["options"]] == ["people", "places", "organisations", "dates", "events"]
        assert q["default"] == [o["id"] for o in q["options"]] == q["answer"]
        assert q["suggestions"] == []
        return
    assert q["options"] == [], "no fixed list of kinds ships"
    assert q["default"] == [] and q["answer"] == [], "an empty answer is every kind"
    assert q["suggestions"] == [], "nothing is suggested before a sample try"


def test_no_other_question_is_open_and_the_closed_ones_keep_their_options():
    for stage in listing(None):
        for q in stage["questions"]:
            if (stage["id"], q["key"]) not in OPEN:
                assert q["open_ended"] is False and q["suggestions"] == [], (stage["id"], q["key"])
    assert _question(listing(None), "normalise", "normalise_how_far")["options"]


def test_a_typed_kind_is_kept_as_typed_and_an_old_text_answer_is_read_as_a_list():
    items = listing(None, {"job_answers": {"statement_kinds": ["Wills", "ship manifests"], "fields": "buyer, seller\nprice"}})
    assert _question(items, "statements", "statement_kinds")["answer"] == ["Wills", "ship manifests"]
    assert _question(items, "structured-data", "fields")["answer"] == ["buyer", "seller", "price"]


def test_a_typed_kind_reaches_the_plan(client, with_material):
    answers = {"purposes": ["entities"], "languages": ["es"], "scripts": ["Latn"], "mac_memory_gb": 64,
               "job_answers": {"entity_kinds": ["ships", "people"]}}
    assembled = client.post("/api/recipes/assemble", json=answers).json()
    (names,) = [s for s in assembled["steps"] if s["job"] == "find-names-tag-words"]
    assert names["settings"] == {"kinds": ["ships", "people"]}


def test_only_a_kinds_answer_a_run_reads_is_marked_read_by_a_step():
    """Review 180: Statements' kinds, Passages' kinds and Structured Data's fields are kept with the answers; no run
    reads them yet, so they are not marked as read (the app says so)."""
    from fichero_server.recipes.start import JOB_ANSWER_SETTINGS

    mapped = {key for key, _ in JOB_ANSWER_SETTINGS.values()}
    items = listing(None)
    for stage, key in OPEN:
        assert _question(items, stage, key)["read_by_a_step"] is (key in mapped), (stage, key)
    assert {"entity_kinds", "calendars"} <= mapped and not {"statement_kinds", "passage_kinds", "fields"} & mapped


def test_names_given_only_typed_kinds_it_has_no_section_for_says_it_finds_every_kind():
    from fichero_server.recipes.start import plan_start

    step = {"id": "names", "job": "find-names-tag-words", "model": {"spacy": "es_core_news_sm", "version": "bundled"},
            "settings": {"kinds": ["ships"]}}
    plan = plan_start({**RECIPE, "steps": [step]}, stays_local=True)
    (run,) = [r for r in plan["runs"] if r["steps"] == ["names"]]
    assert "tool_config" not in run and "every kind" in run["how"] and "ships" in run["how"]
    narrowed = plan_start({**RECIPE, "steps": [{**step, "settings": {"kinds": ["People", "ships"]}}]}, stays_local=True)
    (run,) = [r for r in narrowed["runs"] if r["steps"] == ["names"]]
    assert run["tool_config"] == {"extract_entities_only": {"entity_types": "people"}}


def test_suggestions_hold_only_what_a_sample_try_found():
    tried = {"names": {"names": [{"name": "Istmina", "type": "location"}, {"name": "Juan", "type": "person"},
                                 {"name": "Quito", "type": "location"}]}}
    items = listing(None, None, tried)
    assert _question(items, "names", "entity_kinds")["suggestions"] == ["location", "person"]
    # a stage whose try reported no kinds suggests nothing; the stage that was not tried suggests nothing
    assert _question(items, "statements", "statement_kinds")["suggestions"] == []
    assert _question(listing(None, None, {"names": {"names": []}}), "names", "entity_kinds")["suggestions"] == []
    # a try that reports its kinds (found_kinds) is read once each, trimmed, in the same sorted order as Names' (the
    # test first expected the try's own order; `suggested_kinds` has sorted every source since 04b50149d)
    items = listing(None, None, {"statements": {"found_kinds": ["sale", "Sale", " gift "]}})
    assert _question(items, "statements", "statement_kinds")["suggestions"] == ["gift", "sale"]


def test_passages_says_what_it_does_without_listing_kinds_and_has_an_example():
    """Not listed while no job runs it, but its words and its example from a try stand ready for when it does."""
    from fichero_server.recipes.stages import example_from_samples, get_stage

    passages = get_stage("passages")
    assert passages.sentence and passages.example
    assert "quotation" not in passages.sentence.lower() and "formul" not in passages.sentence.lower()
    assert example_from_samples("passages", None) is None  # until a try returns a passage
    tried = {"passages": [{"page": "p1", "text": "Ante mí, el escribano"}]}
    assert example_from_samples("passages", {"passages": tried["passages"]}) == "Ante mí, el escribano"


def test_every_box_unticked_turns_names_off_and_an_old_empty_answer_is_every_kind():
    """## 1110: [] (an old project) reads every kind; ["none"] (all unticked) skips Names, said in the plan."""
    from fichero_server.recipes.start import plan_start

    step = {"id": "names", "job": "find-names-tag-words", "model": {"spacy": "es_core_news_sm", "version": "bundled"}}
    old = plan_start({**RECIPE, "steps": [{**step, "settings": {"kinds": []}}]}, stays_local=True)
    (run,) = [r for r in old["runs"] if r["steps"] == ["names"]]
    assert "tool_config" not in run and not old["skipped"]
    none = plan_start({**RECIPE, "steps": [{**step, "settings": {"kinds": ["none"]}}]}, stays_local=True)
    assert not [r for r in none["runs"] if r["steps"] == ["names"]]
    assert [s["step"] for s in none["skipped"]] == ["names"] and "unticked" in none["skipped"][0]["why"]
