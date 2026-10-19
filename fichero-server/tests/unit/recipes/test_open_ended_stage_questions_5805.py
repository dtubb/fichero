"""Set Up stage questions that name kinds are open-ended (#5805;
docs/contributor_manual/specs/source/models-chains-and-projects.md, `source.onboard.stages.kinds-are-open-ended` and
`passages-says-what-it-does`).

WHY: the staged build showed Statements and Passages with a FIXED list of kinds (Sales, Gifts…), which the spec had only
as examples. Every such question is now: every kind by default, the person can type their own, and suggestions come
only from what a sample try found."""
from __future__ import annotations

import pytest

from fichero_server.recipes.stages import STAGES, listing

#: The stage questions that name kinds (stage id, answer key).
OPEN = [("names", "entity_kinds"), ("statements", "statement_kinds"), ("dates", "calendars"),
        ("passages", "passage_kinds"), ("structured-data", "fields")]


def _question(items, stage, key):
    return next(q for s in items if s["id"] == stage for q in s["questions"] if q["key"] == key)


@pytest.mark.parametrize(("stage", "key"), OPEN)
def test_every_kinds_question_is_open_with_every_kind_by_default(stage, key):
    q = _question(listing(None), stage, key)
    assert q["open_ended"] is True
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


def test_a_typed_kind_reaches_the_plan(client):
    answers = {"purposes": ["entities"], "languages": ["es"], "scripts": ["Latn"], "mac_memory_gb": 64,
               "job_answers": {"entity_kinds": ["ships", "people"]}}
    assembled = client.post("/api/recipes/assemble", json=answers).json()
    (names,) = [s for s in assembled["steps"] if s["job"] == "find-names-tag-words"]
    assert names["settings"] == {"kinds": ["ships", "people"]}


def test_each_kinds_answer_is_read_by_the_step_it_configures():
    from fichero_server.recipes.start import JOB_ANSWER_SETTINGS

    for stage, key in OPEN:
        jobs = next(s for s in STAGES if s.id == stage).jobs
        assert any(JOB_ANSWER_SETTINGS.get(j, (None,))[0] == key for j in jobs), (stage, key)


def test_suggestions_hold_only_what_a_sample_try_found():
    tried = {"names": {"names": [{"name": "Istmina", "type": "location"}, {"name": "Juan", "type": "person"},
                                 {"name": "Quito", "type": "location"}]}}
    items = listing(None, None, tried)
    assert _question(items, "names", "entity_kinds")["suggestions"] == ["location", "person"]
    # a stage whose try reported no kinds suggests nothing; the stage that was not tried suggests nothing
    assert _question(items, "statements", "statement_kinds")["suggestions"] == []
    assert _question(listing(None, None, {"names": {"names": []}}), "names", "entity_kinds")["suggestions"] == []
    # a try that reports its kinds (found_kinds) is read as is, once each
    items = listing(None, None, {"statements": {"found_kinds": ["sale", "Sale", " gift "]}})
    assert _question(items, "statements", "statement_kinds")["suggestions"] == ["sale", "gift"]


def test_passages_says_what_it_does_without_listing_kinds_and_has_an_example():
    passages = next(s for s in listing(None) if s["id"] == "passages")
    assert passages["sentence"] and passages["example"]
    assert "quotation" not in passages["sentence"].lower() and "formul" not in passages["sentence"].lower()
    assert passages["example_from_samples"] is None  # until a try returns a passage
    tried = {"passages": {"passages": [{"page": "p1", "text": "Ante mí, el escribano"}]}}
    again = next(s for s in listing(None, None, tried) if s["id"] == "passages")
    assert again["example_from_samples"] == "Ante mí, el escribano"
