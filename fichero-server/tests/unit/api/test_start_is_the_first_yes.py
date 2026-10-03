"""Start is the project's first yes (`source.project.automatic-after-first-yes`, #4951).

Why it matters: nothing in a project may run by itself until the person presses Start, having seen
what will run, on how many pages, and what it costs. So the plan is readable before the yes, the
yes is recorded (when, on which recipe version) in the project folder, it is audited and can be
taken back, and a refused Start (a cloud step in a project that keeps its pages here) records
nothing.
"""
from __future__ import annotations

from pathlib import Path

from fichero_server.models import ActionAudit, Document, DocType

RECIPE = {"fichero_recipe": 1, "id": "t/kraken", "version": "0.2.0", "title": "t", "steps": [
    {"id": "lines", "job": "find-lines", "model": {"kraken": "blla", "kraken_version": "bundled"}},
    {"id": "read", "job": "read-a-line", "model": {"zenodo": "10.5281/zenodo.13788177"}},
]}
CLOUD_STEP = {"id": "correct", "job": "correct", "model": {"cloud": "openai", "model": "gpt-5"},
              "runs_on": "cloud:openai"}


def _save(client, recipe, cloud_allowed=False):
    r = client.put("/api/recipes/project", json={"answers": {"purpose": "transcribe",
                                                             "cloud_allowed": cloud_allowed},
                                                 "recipe": recipe})
    assert r.status_code == 200, r.text


def _pages(db):
    pdf = Document(name="deed.pdf", doc_type=DocType.file)
    db.save(pdf)
    for n in (1, 2):
        db.save(Document(name=f"p{n}", doc_type=DocType.page, parent_id=pdf.id, sequence=n))
    db.save(Document(name="letter.jpg", doc_type=DocType.file))


def test_the_plan_is_shown_before_anything_runs_with_the_page_count(client, db):
    """The Start screen reads what will run and on how many pages, and nothing is started yet."""
    _pages(db)
    _save(client, RECIPE)
    plan = client.get("/api/recipes/project/start").json()
    assert plan["started"] is None and plan["refusals"] == []
    assert [w["workflow"] for w in plan["workflows"]] == ["Transcribe (Kraken)"]
    # Two pages of a PDF and one image with no pages; the PDF itself is not a page.
    assert plan["estimate"]["pages"] == 3 and plan["estimate"]["total_cost_usd"] == 0.0


def test_start_records_the_first_yes_and_can_be_taken_back(client, db, test_package):
    """The yes names the recipe version it was given on, lives in the project folder, and is
    undoable like every change."""
    _save(client, RECIPE)
    r = client.post("/api/recipes/project/start")
    assert r.status_code == 200, r.text
    started = r.json()["started"]
    assert started["recipe_id"] == "t/kraken" and started["recipe_version"] == "0.2.0"
    assert started["workflows"] == ["Transcribe (Kraken)"] and started["started_at"]
    assert (Path(test_package) / "recipe" / "started.yaml").is_file()
    [audit] = [a for a in db.query(ActionAudit) if a.action_name == "project.start"]
    assert client.post(f"/api/actions/audit/{audit.id}/undo").status_code == 200
    assert client.get("/api/recipes/project/start").json()["started"] is None


def test_a_refused_start_names_the_step_and_records_nothing(client, test_package):
    """A project that keeps its pages here refuses the cloud step by name; no yes is written."""
    _save(client, {**RECIPE, "steps": RECIPE["steps"] + [CLOUD_STEP]}, cloud_allowed=False)
    r = client.post("/api/recipes/project/start")
    assert r.status_code == 422 and "step correct" in r.text and "off this Mac" in r.text
    assert not (Path(test_package) / "recipe" / "started.yaml").exists()


def _assembled(client):
    r = client.post("/api/recipes/assemble", json={
        "purpose": "transcribe", "languages": ["es"], "scripts": ["Latn"],
        "material": "handwriting", "mac_memory_gb": 16})
    assert r.status_code == 200, r.text
    return r.json()


def test_a_recipe_the_app_saves_from_assemble_is_a_whole_recipe(client):
    """Gap 5: the assemble answer carries the schema, version and suits, so what the app saves
    passes the same check as a recipe folder, and Start can record which version it ran."""
    recipe = _assembled(client)
    assert recipe["fichero_recipe"] == 1 and recipe["version"] and recipe["suits"]["scripts"] == ["Latn"]
    assert client.post("/api/recipes/check", json={"recipe": recipe}).json()["problems"] == []


def test_the_default_spanish_handwriting_recipe_is_refused_only_for_its_reader(client):
    """The rules pick PP-OCRv6 for Latin handwriting (the reader with a published CER), and this
    Mac's Kraken cannot fetch it: that, and nothing else, is what stops Start."""
    _save(client, _assembled(client))
    refusals = client.get("/api/recipes/project/start").json()["refusals"]
    assert len(refusals) == 1 and "21788410" in refusals[0], refusals


def test_with_a_reader_this_mac_can_fetch_the_default_recipe_starts_and_records_its_version(client):
    """Swap the reader for McCATMuS (as a person can in the Inspector) and the same assembled
    recipe starts: the yes names the recipe's version and both runs."""
    recipe = _assembled(client)
    for step in recipe["steps"]:
        if step["job"] == "read-a-line":
            step["model"] = {"zenodo": "10.5281/zenodo.13788177"}
    _save(client, recipe)
    r = client.post("/api/recipes/project/start")
    assert r.status_code == 200, r.text
    started = r.json()["started"]
    assert started["recipe_version"] == recipe["version"]
    assert started["workflows"] == ["Transcribe (Kraken)", "Paleographer Review"]
