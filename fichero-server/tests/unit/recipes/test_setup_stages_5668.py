"""Set Up, one page per stage: the stages come from the engine (#5668, section 7c).

WHY: the setup window, the Inspector and the manual must say the same thing about each stage, and the app must work
none of it out: which stages there are, in what order, which jobs each carries, what it asks, what it needs, and
whether it can be tried on the person's pages before Start.
"""

from __future__ import annotations

from fichero_server.recipes.jobs import get_job
from fichero_server.recipes.stages import STAGES

#: Section 7d's pipeline order (Daniel, 2026-10-11): Find Regions before Find Lines; Normalise apart from Translate.
#: Leave Out sits between Find Lines and Read (#6070).
ORDER = ["prepare-images", "find-regions", "find-lines", "leave-out", "read", "normalise", "translate", "organise", "names",
         "statements", "dates", "structured-data", "search", "catalogue", "sharing"]
#: Passages waits for its job (`source.job.pull-out-passages`): the stage exists, but Set Up does not offer it.
WAITING = ["passages"]


def test_the_offered_stages_in_pipeline_order_each_job_registered_and_each_need_a_stage(client):
    """`source.onboard.stages.stages-list-from-the-engine` and `needs-are-ticked`."""
    r = client.get("/api/recipes/stages")
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert [s["id"] for s in items] == ORDER and r.json()["count"] == len(ORDER)
    ids = set(ORDER)
    assert not set(WAITING) & {s["id"] for s in items}  # a stage no job runs is not asked about
    for stage in items:
        if stage["id"] == "sharing":  # questions only: no job, no example (`sharing.setup-stage-is-offered-without-jobs`)
            continue
        assert stage["title"] and stage["sentence"] and stage["example"]
        assert stage["jobs"] and all(get_job(j) is not None for j in stage["jobs"]), stage["jobs"]
        assert all(n["stage"] in ids and n["why"].endswith(f"needs {next(s['title'] for s in items if s['id'] == n['stage'])}")
                   for n in stage["needs"])
    by_id = {s["id"]: s for s in items}
    assert next(q for q in by_id["translate"]["questions"])["kind"] == "language"
    assert "normalise_how_far" in [q["key"] for q in by_id["normalise"]["questions"]]
    assert [n["why"] for n in by_id["dates"]["needs"]] == ["Dates & Times needs Names"]
    assert by_id["read"]["tried_by"] == "bake-off" and by_id["find-lines"]["tried_by"] == "bake-off"
    assert by_id["names"]["sampleable"] and by_id["names"]["tried_by"] == "workflow"
    # A job belongs to one stage, except Translate, which shares Normalise's job until it has its own.
    jobs = [j for s in STAGES if s.id != "translate" for j in s.jobs]
    assert len(jobs) == len(set(jobs))


def test_each_need_is_a_stage_whose_jobs_give_what_it_takes():
    """A stated need is real in the job registry: the needed stage gives a kind the needing stage's jobs take."""
    by_id = {s.id: s for s in STAGES}
    for stage in STAGES:
        takes = {alt for j in stage.jobs for kind in get_job(j).takes for alt in kind.split("|")}
        for need in stage.needs:
            gives = {k for j in by_id[need].jobs for k in get_job(j).gives}
            assert takes & gives, (stage.id, need)


def test_without_a_project_every_stage_is_off_with_its_defaults(client, monkeypatch):
    from fichero_server.api.routes.system import recipes

    monkeypatch.setattr(recipes, "_optional_library", lambda request: None)
    items = client.get("/api/recipes/stages").json()["items"]
    assert not any(s["on"] for s in items)
    names = next(s for s in items if s["id"] == "names")
    kinds = next(q for q in names["questions"] if q["key"] == "entity_kinds")
    assert kinds["answer"] == kinds["default"] == [o["id"] for o in kinds["options"]] and kinds["read_by_a_step"]  # all ticked: every kind (#5805)
    assert [o["id"] for o in kinds["options"]] == ["people", "places", "organisations", "dates", "events"]


def test_a_projects_recipe_and_answers_say_which_stages_are_on(client, with_material):
    answers = {"purposes": ["transcribe", "entities"], "languages": ["es"], "scripts": ["Latn"],
               "materials": ["handwriting"], "job_answers": {"entity_kinds": ["people"]}}
    recipe = client.post("/api/recipes/assemble", json=answers).json()
    assert client.put("/api/recipes/project", json={"answers": answers, "recipe": recipe}).status_code == 200

    items = {s["id"]: s for s in client.get("/api/recipes/stages").json()["items"]}

    assert items["read"]["on"] and items["names"]["on"] and items["find-lines"]["on"]
    assert not items["translate"]["on"] and not items["search"]["on"]
    kinds = next(q for q in items["names"]["questions"] if q["key"] == "entity_kinds")
    assert kinds["answer"] == ["people"]  # the project's answer, not the default


def test_every_offered_stage_has_a_job_that_runs_or_a_way_by_hand_and_a_waiting_stage_has_none(client):
    """Passages asked its question and Start then said 'nothing in Fichero does this yet' (spec review 2026-10-20)."""
    from fichero_server.recipes.stages import offered
    from fichero_server.recipes.start import BY_HAND_FIX, start_runs

    for stage in STAGES:
        runs = any(start_runs(j) or j in BY_HAND_FIX for j in stage.jobs)
        if not stage.jobs and stage.questions:  # questions only (Sharing and accounts): offered for its questions
            assert offered(stage) and stage.id not in WAITING
            continue
        assert offered(stage) is runs
        assert (stage.id in WAITING) is (not runs), stage.id


def _prepare_stage(client, job_answers=None):
    """The Prepare Images stage as the listing serves it for a project that answered `job_answers`."""
    if job_answers is not None:
        r = client.put("/api/recipes/project", json={"answers": {"purposes": ["transcribe"], "job_answers": job_answers}})
        assert r.status_code == 200, r.text
    return next(s for s in client.get("/api/recipes/stages").json()["items"] if s["id"] == "prepare-images")


def test_wide_prepare_images_lists_four_operations_in_order(client, with_material):
    """`wide.prepare.four-operations-listed`: split, straighten, crop, clarity, each with its id, the engine's sentence, its
    default from the questions and whether it is on; no other stage has operations."""
    items = client.get("/api/recipes/stages").json()["items"]
    prepare = next(s for s in items if s["id"] == "prepare-images")
    assert [o["id"] for o in prepare["operations"]][:4] == ["split", "straighten", "crop", "clarity"]  # the rest of the suite follows, off
    assert all(o["title"] and o["sentence"] for o in prepare["operations"])
    assert [s["id"] for s in items if s["operations"]] == ["prepare-images"]


def test_wide_the_operations_defaults_follow_the_questions(client, with_material):
    """Split follows 'Two pages in one picture?'; straighten and crop are on; clarity is on for faded paper, off for ruled
    paper, and with no paper answer it is on and says Fichero looks at each page (ruled 2026-10-31, Q5)."""
    plain = {o["id"]: o for o in _prepare_stage(client, {})["operations"]}
    assert (plain["split"]["on"], plain["straighten"]["on"], plain["crop"]["on"], plain["clarity"]["on"]) == (False, True, True, True)
    assert plain["clarity"]["note"] == "Fichero looks at each page and raises only the faded ones"
    assert not any(o["by_hand"] for o in plain.values())
    two = {o["id"]: o for o in _prepare_stage(client, {"two_pages_per_image": True, "the_paper": ["faded"]})["operations"]}
    assert two["split"]["on"] and two["clarity"]["on"] and two["clarity"]["note"] is None
    ruled = {o["id"]: o for o in _prepare_stage(client, {"the_paper": ["ruled"]})["operations"]}
    assert ruled["clarity"]["on"] is False and ruled["clarity"]["default"] is False


def test_wide_an_operation_switched_by_hand_wins_over_its_question(client, with_material):
    """`prepare_operations` is the ids that are on; it wins over the questions, which keep setting the defaults."""
    stage = _prepare_stage(client, {"the_paper": ["faded"], "prepare_operations": ["crop", "split"]})
    ops = {o["id"]: o for o in stage["operations"]}
    assert [i for i, o in ops.items() if o["on"]] == ["split", "crop"]
    assert ops["clarity"]["default"] is True and ops["clarity"]["on"] is False, "the question's default stays; the hand wins"
    assert all(o["by_hand"] for o in ops.values())
    assert [q["key"] for q in stage["questions"]] == ["two_pages_per_image", "beside_the_page", "the_paper", "check_missed_lines"]


def test_wide_an_unknown_operation_is_refused_in_words(client, with_material):
    r = client.put("/api/recipes/project", json={"answers": {"job_answers": {"prepare_operations": ["crop", "nonsense"]}}})
    assert r.status_code == 422 and "nonsense" in r.text and "split" in r.text


#: Section J of wide-onboarding.md, job by job: does the step call a model a person can choose?
CALLS_A_MODEL = {
    "find-regions": True, "find-lines": True, "read-a-line": True, "read-a-page": True, "tie-text-to-lines": True, "correct": True,
    "translate-transliterate-normalise": True, "split-into-entries": True, "find-names-tag-words": True,
    "find-statements": True, "extract-to-a-table": True, "describe-for-the-catalogue": True, "make-a-vector": True,
    "split-pages": False, "prepare-the-image": False, "leave-out": False, "find-where-readers-disagree": False,
    "find-documents-in-a-folder": False, "place-in-a-gazetteer": False, "link-to-authorities": False, "work-out-dates": False,
}


def test_wide_every_stage_jobs_row_shape_follows_the_registry_as_section_j_says(client):
    """`wide.picker.row-shape-from-the-registry`: the row is a chooser or 'Fichero does this one', decided by the registry's
    `needs_a_model` alone; every job a stage offers is in the table, and the table agrees with the registry."""
    from fichero_server.recipes.stages import offered, runs_or_by_hand

    jobs = {j["id"]: j for j in client.get("/api/recipes/jobs").json()["items"]}
    offered_jobs = {j for s in STAGES if offered(s) for j in s.jobs if runs_or_by_hand(j)}
    assert offered_jobs <= set(CALLS_A_MODEL), f"a job a stage offers is not in section J's table: {sorted(offered_jobs - set(CALLS_A_MODEL))}"
    for job, calls in CALLS_A_MODEL.items():
        assert jobs[job]["needs_a_model"] is calls, job
        by_hand = job in ("place-in-a-gazetteer", "link-to-authorities", "find-where-readers-disagree")  # the row names the by-hand tool or the plan's own readers instead
        assert bool(jobs[job]["how_it_works"]) is (not calls and not by_hand), job
