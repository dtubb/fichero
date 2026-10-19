"""Set Up, one page per stage: the stages come from the engine (#5668, section 7c).

WHY: the setup window, the Inspector and the manual must say the same thing about each stage, and the app must work
none of it out: which stages there are, in what order, which jobs each carries, what it asks, what it needs, and
whether it can be tried on the person's pages before Start.
"""

from __future__ import annotations

from fichero_server.recipes.jobs import get_job
from fichero_server.recipes.stages import STAGES

#: Section 7d's pipeline order (Daniel, 2026-10-11): Find Regions before Find Lines; Normalise apart from Translate.
ORDER = ["prepare-images", "find-regions", "find-lines", "read", "normalise", "translate", "organise", "names",
         "statements", "dates", "passages", "structured-data", "search"]


def test_the_thirteen_stages_in_pipeline_order_each_job_registered_and_each_need_a_stage(client):
    """`source.onboard.stages.stages-list-from-the-engine` and `needs-are-ticked`."""
    r = client.get("/api/recipes/stages")
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert [s["id"] for s in items] == ORDER and r.json()["count"] == 13
    ids = set(ORDER)
    for stage in items:
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
    assert kinds["answer"] == kinds["default"] == [] and kinds["read_by_a_step"]  # every kind (#5805)


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
