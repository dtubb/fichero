"""Set Up's Sharing and accounts stage (docs/contributor_manual/specs/source/sharing-two-macs.md §10.2, Step 4.1):
`sharing.setup-stage-is-offered-without-jobs`, `sharing.setup-stage-wording`.

WHY: a stage with no job was never listed, so the two sharing questions could not be asked on the page. The engine now
lists it (questions only, last, nothing pre-answered) and keeps the two answers with the library's other Set Up answers;
sharing and accounts themselves stay the Mac's engine state, so nothing here runs at Start.
"""

from __future__ import annotations

SENTENCE = ("Decide now whether other people or your other devices can open this library, and whether each person gets their "
            "own account. You can leave both off and change this later.")


def _stage(client):
    r = client.get("/api/recipes/stages")
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    return items, next(s for s in items if s["id"] == "sharing")


def test_the_sharing_stage_is_listed_last_with_no_jobs(client):
    items, stage = _stage(client)
    assert items[-1]["id"] == "sharing", "after the material stages"
    assert stage["jobs"] == [] and stage["on"] is False and stage["needs"] == []


def test_it_asks_the_two_questions_verbatim_in_order_and_neither_is_pre_answered(client):
    _, stage = _stage(client)
    assert [(q["key"], q["ask"], q["kind"], q["default"], q["answer"]) for q in stage["questions"]] == [
        ("sharing_open_to_others", "Let other people or your other Macs open this library?", "yes-no", False, False),
        ("accounts_each_person", "Give each person their own account?", "yes-no", False, False),
    ]


def test_the_stage_is_in_the_documented_words_with_no_internals(client):
    _, stage = _stage(client)
    assert stage["title"] == "Sharing and accounts" and stage["sentence"] == SENTENCE and stage["example"] == ""
    text = " ".join([stage["sentence"], *[q["ask"] for q in stage["questions"]]]).lower()
    for word in ("pin", "certificate", "https", "restart", "port", "token"):
        assert word not in text.split(), word


def test_the_answers_round_trip_with_the_projects_answers(client):
    saved = client.put("/api/recipes/project", json={"answers": {
        "purposes": ["transcribe"], "job_answers": {"sharing_open_to_others": True, "accounts_each_person": True}}})
    assert saved.status_code == 200, saved.text
    _, stage = _stage(client)
    assert [q["answer"] for q in stage["questions"]] == [True, True]
