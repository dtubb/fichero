"""Setup, round 2: the engine half (section 7b of `source/models-chains-and-projects.md`, ruled 2026-10-05).

Why it matters: the maintainer tested setup and found that a project could have only one purpose and
one kind of material, that "spanish" typed into the language field reached the rules as a word (so
every reader was refused, since cards list tags), that a step's problem was the rules' raw reason with
model ids in it, and that first run had no project to save into (#5477 to #5482). Each test goes
through the real routes, so the app, MCP and the command line see exactly what is pinned here.
"""
from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

import yaml
from fastapi.testclient import TestClient

TRANSCRIBE = ["find-lines", "read-a-line", "correct"]


def _assemble(client, **answers):
    body = {"languages": ["es"], "scripts": ["Latn"], "mac_memory_gb": 16, **answers}
    return client.post("/api/recipes/assemble", json=body)


def _jobs(recipe: dict) -> list[str]:
    return [s["job"] for s in recipe["steps"]]


# --- Purposes are checkboxes (#5478, source.onboard.purpose-sets-layers) ----------------------------


def test_several_purposes_give_the_union_of_their_jobs_each_once_in_step_order(client):
    """WHY: a project can be for any combination of purposes; if the union repeated a job, Start would
    read every page twice, and if the order followed the ticking, the same answers would give two
    recipes (the spec's own test case: transcribe, map places, search)."""
    r = _assemble(client, purposes=["transcribe", "map-places", "search"])
    assert r.status_code == 200, r.text
    assert _jobs(r.json()) == [*TRANSCRIBE, "find-names-tag-words", "place-in-a-gazetteer", "make-a-vector"]
    again = _assemble(client, purposes=["search", "map-places", "transcribe"]).json()
    assert again["steps"] == r.json()["steps"] and again["id"] == r.json()["id"]
    assert r.json()["purposes"] == ["transcribe", "search", "map-places"]  # in the order setup offers them


def test_each_step_carries_its_topic(client):
    """WHY: setup shows each step by its topic's title and one sentence (screen 6); the words must be
    the registry's, written once, not a second copy in the app."""
    steps = _assemble(client, purposes=["transcribe"]).json()["steps"]
    read = next(s for s in steps if s["job"] == "read-a-line")
    topic = client.get("/api/topics/read-a-line").json()
    assert read["topic"] == "read-a-line" and read["title"] == topic["title"]
    assert read["sentence"] == topic["short"]


def test_every_purpose_lists_its_jobs_and_the_new_purposes_are_offered(client):
    """WHY: under each ticked purpose setup lists its jobs by title (source.onboard.purposes-show-their-jobs);
    Statements, Translate or normalise, Gather quotations, Catalogue and Tables are among the checkboxes."""
    items = {p["id"]: p for p in client.get("/api/recipes/purposes").json()["items"]}
    for new in ("statements", "translate-normalise", "quotations", "catalogue", "tables"):
        assert new in items and items[new]["runs_by_itself"] is True
    assert [j["title"] for j in items["map-places"]["jobs"]] == [
        "Find lines", "Read each line", "Correct", "Find names", "Place in a gazetteer"]
    assert items["decipher"]["jobs"] == [] and items["not-sure"]["jobs"] == []


def test_every_registered_job_can_be_ticked_on_its_own_and_takes_its_place_in_the_order(client):
    """WHY: every job is a checkbox (ruled 2026-10-05). A job the step order did not know could be
    ticked but never placed; a job ticked on its own joins the purposes' jobs once, in order."""
    from fichero_server.recipes.assemble import STEP_ORDER
    from fichero_server.recipes.jobs import all_jobs

    assert sorted(STEP_ORDER) == sorted(j.id for j in all_jobs())
    r = _assemble(client, purposes=["transcribe"], jobs=["export", "put-in-order", "correct"])
    assert _jobs(r.json()) == ["find-lines", "put-in-order", "read-a-line", "correct", "export"]
    refused = _assemble(client, purposes=["transcribe"], jobs=["tell-hands-apart"])
    assert refused.status_code == 422 and "no job 'tell-hands-apart'" in refused.text


def test_a_purpose_fichero_does_not_have_is_refused_in_words(client):
    r = _assemble(client, purposes=["transcribe", "astrology"])
    assert r.status_code == 422 and "no purpose 'astrology'" in r.text


# --- Material is checkboxes (#5478, source.onboard.material-any-mix) ------------------------------


def test_several_materials_get_one_reader_each(client):
    """WHY: a project of letters and printed forms needs a reader for each; one reader for all would read
    the print with the handwriting model or the reverse."""
    recipe = _assemble(client, purposes=["transcribe"], materials=["print", "handwriting"]).json()
    read = next(s for s in recipe["steps"] if s["job"] == "read-a-line")
    assert [r["material"] for r in read["readers"]] == ["handwriting", "print"]
    assert read["material"] == "handwriting"  # the default until an override says which applies where
    assert recipe["suits"]["material"] == ["handwriting", "print"]
    assert _jobs(recipe).count("read-a-line") == 1  # one step, so Start reads each page once


# --- Old single answers still read (no data loss) -------------------------------------------------


def test_a_project_saved_with_one_purpose_reads_as_a_list_of_one(client, test_package):
    """WHY: projects set up before 2026-10-05 hold `purpose` and `material`; reading them must neither
    fail nor drop the answer, and what reads them (the layers, the import hand-off) must still work."""
    folder = Path(test_package) / "recipe"
    folder.mkdir()
    (folder / "setup.yaml").write_text(yaml.safe_dump({
        "purpose": "entities", "material": "print", "languages": ["es"], "scripts": ["Latn"], "pages": 12}))
    answers = client.get("/api/recipes/project").json()["answers"]
    assert answers["purposes"] == ["entities"] and answers["materials"] == ["print"]
    assert "purpose" not in answers and "material" not in answers
    assert answers["languages"] == ["es"] and answers["pages"] == 12
    assert answers["directions"] == {"Latn": "ltr"}
    addable = client.get("/api/recipes/project/start").json()["addable"]
    assert "entities" not in addable and addable  # its purpose's layer is known as its own


def test_the_old_single_purpose_request_still_assembles(client):
    r = _assemble(client, purpose="transcribe", material="print")
    assert r.status_code == 200, r.text
    assert _jobs(r.json()) == TRANSCRIBE and r.json()["suits"]["material"] == ["print"]


# --- Languages are tags (#5479, source.onboard.language-stored-as-tag) ----------------------------


def test_a_typed_language_name_is_saved_as_its_tag(client):
    """WHY: "spanish" reached the rules as typed and every reader was refused, since cards list `es`."""
    r = client.put("/api/recipes/project", json={"answers": {
        "purposes": ["entities"], "languages": ["spanish"], "scripts": ["latin"]}, "recipe": None})
    assert r.status_code == 200, r.text
    answers = client.get("/api/recipes/project").json()["answers"]
    assert answers["languages"] == ["es"] and answers["scripts"] == ["Latn"]
    names = next(s for s in _assemble(client, purposes=["entities"], languages=["spanish"]).json()["steps"]
                 if s["job"] == "find-names-tag-words")
    assert names.get("model") and "problem" not in {k for k, v in names.items() if v}


def test_an_unknown_language_word_is_refused_in_words_and_nothing_is_saved(client, test_package):
    r = client.put("/api/recipes/project", json={"answers": {
        "purposes": ["transcribe"], "languages": ["klingonese"], "scripts": ["Latn"]}, "recipe": None})
    assert r.status_code == 422
    assert "Fichero doesn't know the language 'klingonese'. Choose it from the list." in r.text
    assert not (Path(test_package) / "recipe" / "setup.yaml").exists()
    assert _assemble(client, purposes=["transcribe"], languages=["klingonese"]).status_code == 422


# --- Direction is an answer (#5479, source.onboard.direction-chosen) ------------------------------


def test_direction_is_prefilled_from_the_script_and_a_change_is_kept(client):
    """WHY: direction was shown but never chosen; a person whose Arabic-script pages are laid out
    otherwise had no way to say so."""
    client.put("/api/recipes/project", json={"answers": {
        "purposes": ["transcribe"], "languages": ["ar"], "scripts": ["Arab"]}, "recipe": None})
    assert client.get("/api/recipes/project").json()["answers"]["directions"] == {"Arab": "rtl"}
    client.put("/api/recipes/project", json={"answers": {
        "purposes": ["transcribe"], "languages": ["ar"], "scripts": ["Arab"], "directions": {"Arab": "ltr"}},
        "recipe": None})
    assert client.get("/api/recipes/project").json()["answers"]["directions"] == {"Arab": "ltr"}
    bad = client.put("/api/recipes/project", json={"answers": {
        "purposes": ["transcribe"], "languages": ["ar"], "scripts": ["Arab"], "directions": {"Arab": "upwards"}},
        "recipe": None})
    assert bad.status_code == 422 and "'upwards' for Arab" in bad.text


# --- A step's problem is one structured reason (#5481, source.onboard.says-no-model) -------------


def test_a_step_with_no_model_has_one_problem_in_words_with_its_fix_and_no_raw_ids(client):
    """WHY: setup showed the rules' raw reason, model ids and all, twice. The sentence is what a
    historian reads; the raw reason stays, apart, for the Inspector and the log."""
    recipe = _assemble(client, purposes=["transcribe"], languages=["chr"], scripts=["Cher"]).json()
    read = next(s for s in recipe["steps"] if s["job"] == "read-a-line")
    problem = read["problem"]
    assert problem["kind"] == "no-model-for-script"
    assert problem["sentence"] == "No reading model here reads Cherokee yet."
    assert problem["fix"] == "download" and problem["fixes"][0] == "download"
    assert "kraken:" in problem["detail"]  # the raw reason, kept apart
    for step in recipe["steps"]:
        if step.get("problem"):
            sentence = step["problem"]["sentence"]
            assert not any(raw in sentence for raw in ("mlx:", "hf/", "@", "kraken:", "zenodo", "Qwen"))
    # The recipe, problems and all, can be saved as it was proposed (a recipe refuses keys like `code`).
    saved = client.put("/api/recipes/project", json={"answers": None, "recipe": recipe})
    assert saved.status_code == 200, saved.text


def test_a_language_refusal_names_the_language(client):
    """The spec's own case: a correcting step refused for language says which language, in words."""
    from fichero_server.recipes.assemble import Answers, Card, assemble

    qwen = Card("mlx:hf/mlx-community/Qwen@unpinned", {"hf": "q", "revision": "main"}, frozenset({"correct"}),
                frozenset({"Latn"}), frozenset({"en"}), frozenset({"handwriting"}))
    step = assemble(Answers(purposes=("transcribe",), languages=frozenset({"es"}), scripts=frozenset({"Latn"})),
                    [qwen])["steps"][2]
    assert step["problem"]["kind"] == "no-model-for-language"
    assert step["problem"]["sentence"] == "No correcting model here knows Spanish yet."
    assert "mlx:" in step["problem"]["detail"] and "mlx:" not in step["problem"]["sentence"]


# --- First run: create the project, then save into it (#5477, #5482) ------------------------------


def test_first_run_creates_the_project_then_setup_saves_and_plans_in_it(tmp_path):
    """WHY: first run saved through the app-wide client, with no project path, so every save answered
    400 and Start never enabled. Through the one create path (POST /api/library) and then the new
    project's own path, the setup routes work straight away."""
    from fichero_server.api.auth import initialize_token
    from fichero_server.api.main import app
    from fichero_server.db import db_manager

    app.dependency_overrides.clear()
    client = TestClient(app)
    client.headers["Authorization"] = f"Bearer {initialize_token()}"
    package = tmp_path / "Fichero" / "My Project.fichero"
    try:
        created = client.post("/api/library", json={"path": str(package)})
        assert created.status_code == 200, created.text
        headers = {"X-Fichero-Library-Path": quote(str(package), safe="/")}
        assert client.get("/api/recipes/project").status_code == 400  # no project named: the old bug's shape
        saved = client.put("/api/recipes/project", headers=headers, json={"answers": {
            "purposes": ["transcribe", "search"], "languages": ["spanish"], "scripts": ["Latn"],
            "materials": ["handwriting"]}, "recipe": None})
        assert saved.status_code == 200, saved.text
        back = client.get("/api/recipes/project", headers=headers).json()
        assert back["answers"]["purposes"] == ["transcribe", "search"] and back["answers"]["languages"] == ["es"]
        assert (package / "recipe" / "setup.yaml").is_file()
        plan = client.get("/api/recipes/project/start", headers=headers)
        assert plan.status_code == 200, plan.text
    finally:
        db_manager.close_all()
