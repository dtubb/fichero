"""The model finder's engine half (#5612), tested to the spec
(docs/contributor_manual/specs/source/models-chains-and-projects.md, `source.find.app-card-actions`).

Through the public routes the app calls: `GET /api/recipes/candidates` (each candidate names its download action,
whether it is installed and where it runs), `GET /api/recipes/jobs` (which jobs read the material),
`POST /api/recipes/project/steps/use-candidate` (any candidate as a step's reader, audited and undoable) and the Start
plan. Only this Mac's model store is stubbed (`mac`): nothing is downloaded or loaded.
"""
from __future__ import annotations

from tests.unit.recipes.test_installed_model_first_to_spec import mac  # noqa: F401  (fixture)
from tests.unit.recipes.test_recipe_execution_to_spec import _recipe, _save, engine, pages  # noqa: F401

LINES = {"id": "lines", "job": "find-lines", "model": {"kraken": "blla", "kraken_version": "bundled"}}
READ = {"id": "read", "job": "read-a-line", "model": {"zenodo": "10.5281/zenodo.13788177"}}
PAGE = {"id": "page", "job": "read-a-page", "model": {"zenodo": "10.5281/zenodo.13788177"}}


def _candidates(client, job="read-a-page"):
    r = client.get("/api/recipes/candidates", params={"job": job, "scripts": "Latn", "languages": "en"})
    assert r.status_code == 200, r.text
    return r.json()["items"]


def test_each_candidate_names_its_download_installed_and_place(client, mac):
    """An MLX reader not on this Mac names the download the Start plan would (model.download, runtime and id) and
    says it is not installed; once installed there is nothing to download. Every candidate says where it runs."""
    items = _candidates(client)
    assert items and all(i["runs_where"] in ("this_mac", "own_machine", "provider") for i in items)
    mlx = [i for i in items if "hf" in i["pin"] and i["runs_where"] == "this_mac"]
    assert mlx, [i["id"] for i in items]
    first = mlx[0]
    assert first["installed"] is False
    download = first["download"]
    assert download["action"] == "model.download" and download["runtime"] == "mlx"
    assert download["params"] == {"runtime": "mlx", "model": download["model"]}
    mac.installed.add(download["model"])
    again = next(i for i in _candidates(client) if i["id"] == first["id"])
    assert again["installed"] is True and again["download"] is None
    cloud = [i for i in items if i["id"].startswith("cloud") or "cloud" in i["pin"]]
    assert all(i["runs_where"] == "provider" and i["download"] is None for i in cloud)


def test_jobs_say_which_read_the_material(client):
    """The app reads which jobs a reader does from the registry, not its own copy of the list."""
    jobs = {j["id"]: j["reads_material"] for j in client.get("/api/recipes/jobs").json()["items"]}
    assert {j for j, reads in jobs.items() if reads} == {"read-a-line", "read-a-page"}


def test_any_candidate_becomes_the_steps_reader_audited_and_undoable(client, db, pages, mac):
    """"Use for This Step" on any candidate: the step reads with it, kept as the project's override (as use-instead
    and Use This keep theirs); the Start plan then offers its download; one undo restores the step."""
    _save(client, _recipe(None, LINES, PAGE), cloud_allowed=False)
    candidate = next(i for i in _candidates(client) if "hf" in i["pin"] and i["download"])
    used = client.post("/api/recipes/project/steps/use-candidate", json={"step": "page", "card": candidate["id"]})
    assert used.status_code == 200, used.text
    step = next(s for s in used.json()["recipe"]["steps"] if s["id"] == "page")
    assert step["model"] == candidate["pin"]
    [override] = used.json()["recipe"]["overrides"]
    assert (override["step"], override["scope"], override["card"]) == ("page", "project", candidate["id"])
    assert "chosen by you" in override["because"]

    plan = client.get("/api/recipes/project/start").json()
    assert [d["params"] for d in plan["downloads"] if d["runtime"] == "mlx"] == [candidate["download"]["params"]]

    audit = client.get("/api/actions/audit").json()["items"][0]
    assert audit["action_name"] == "project.save_setup"
    assert client.post(f"/api/actions/audit/{audit['id']}/undo").status_code == 200
    back = client.get("/api/recipes/project").json()["recipe"]
    assert next(s for s in back["steps"] if s["id"] == "page")["model"] == PAGE["model"]
    assert not back.get("overrides")


def test_use_candidate_refuses_in_words(client, db, pages, mac):
    """A card Fichero has not found, a step the recipe lacks, or a card that does not do the step's job is refused."""
    _save(client, _recipe(None, LINES, READ), cloud_allowed=False)
    page_only = next(i for i in _candidates(client) if "read-a-line" not in i["jobs"])
    post = lambda body: client.post("/api/recipes/project/steps/use-candidate", json=body)  # noqa: E731
    r = post({"step": "read", "card": "mlx:hf/nobody/nothing@unpinned"})
    assert r.status_code == 422 and "not a model Fichero has found" in r.json()["detail"]
    r = post({"step": "nope", "card": page_only["id"]})
    assert r.status_code == 422 and "no step 'nope'" in r.json()["detail"]
    r = post({"step": "read", "card": page_only["id"]})
    assert r.status_code == 422 and "does not do the step 'read'" in r.json()["detail"]
