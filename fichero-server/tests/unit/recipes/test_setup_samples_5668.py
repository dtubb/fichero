"""Your Material's two questions, the sample pages (`source.onboard.samples-first`), and trying a stage on them before
Start (#5668, section 7c).

WHY: the person must see each stage work on a few of their own pages before Start, and nothing may be written as
the project's work by it: a try that left names or readings in the project would make Start skip pages as done, and
the person could not tell a sample from the work. The period and the hand must reach the search for readers, or a
Kurrent hand gets readers made for Caroline minuscule.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from fichero_server.execution import jobs
from fichero_server.models import ContentRepresentation, DocType, Document, FileType, SegmentPass
from fichero_server.models.knowledge import KnowledgeEntity
from fichero_server.recipes import discovery, samples
from fichero_server.recipes.hands import hands_for, period_years, tags_for


# --- Your Material: when written, which hand --------------------------------------------------------------------


def test_the_hands_offered_follow_the_script_and_the_century(client):
    fifteenth = {h.id for h in hands_for("Latn", "15th century")}
    assert {"gothic-textualis", "gothic-cursiva", "humanistic", "secretary", "italic"} <= fifteenth
    assert not {"kurrent", "copperplate", "caroline-minuscule"} & fifteenth
    eighteenth = {h.id for h in hands_for("Latn", "1700–1780")}
    assert {"kurrent", "copperplate", "italic", "spanish-humanistic-cursive"} <= eighteenth
    assert not {"caroline-minuscule", "gothic-textualis"} & eighteenth
    assert period_years("16th century") == (1501, 1600) and period_years("1650-1700") == (1650, 1700)
    listed = client.get("/api/recipes/hands", params={"script": "Latn", "period": "18th century"}).json()
    kurrent = next(h for h in listed["items"] if h["id"] == "kurrent")
    assert kurrent["tags"] == ["kurrent"] and kurrent["centuries"] == "16th–20th century" and kurrent["looks"]
    assert listed["period_years"] == [1701, 1800] and listed["not_sure"] == "not-sure"


def test_the_period_and_hand_are_saved_with_the_answers(client):
    answers = {"purposes": ["transcribe"], "languages": ["de"], "scripts": ["Latn"], "materials": ["handwriting"],
               "period": "1650–1700", "place": "Istmina, Chocó", "hands": ["kurrent", "a hand of my own", "not-sure"]}
    recipe = client.post("/api/recipes/assemble", json=answers)
    assert recipe.status_code == 200, recipe.text
    saved = client.put("/api/recipes/project", json={"answers": answers, "recipe": recipe.json()}).json()
    assert saved["answers"]["period"] == "1650–1700" and saved["answers"]["place"] == "Istmina, Chocó"
    assert saved["answers"]["hands"] == ["kurrent", "a hand of my own", "not-sure"]  # typed kept as typed
    assert tags_for(saved["answers"]["hands"]) == ["kurrent", "a-hand-of-my-own"]


def test_a_kurrent_hand_asks_the_reader_search_for_kurrent(monkeypatch, tmp_path):
    monkeypatch.setenv("FICHERO_MODEL_STORE_ROOT", str(tmp_path / "store"))
    asked = []

    async def fetch(task=None, search=None, sort="downloads", limit=20, offset=0, library=None, tags=None):
        asked.append(tuple(tags or ()))
        return []

    monkeypatch.setattr("fichero_server.api.routes.ai.models._fetch_hf_models", fetch)
    asyncio.run(discovery.search_hugging_face(frozenset({"de"}), hand_tags=tags_for(["kurrent"])))
    assert ("kurrent",) in asked and ("de", "kurrent") in asked


# --- the samples ------------------------------------------------------------------------------------------------


def _pages(db, tmp_path, n: int) -> list[Document]:
    out = []
    for i in range(n):
        path = tmp_path / "scans" / f"p{i:03d}.jpg"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x" * (1000 + (i * 37) % 500 + (5000 if i == 7 else 0) - (900 if i == 11 else 0)))
        doc = Document(name=path.name, doc_type=DocType.file, file_type=FileType.image, path=str(path),
                       page_content="Muy señor mío")  # a page with text: Names needs Read (#5687)
        db.save(doc)
        out.append(doc)
    return out


@pytest.mark.parametrize("n", [1, 4])
def test_a_small_project_samples_every_page(db, tmp_path, n):
    pages = _pages(db, tmp_path, n)
    assert [p["id"] for p in samples.propose(db)] == [p.id for p in pages]


def test_a_large_project_samples_five_spread_across_it(db, tmp_path):
    pages = _pages(db, tmp_path, 200)
    proposed = samples.propose(db)
    ids = [p["id"] for p in proposed]
    assert len(ids) == 5 and len(set(ids)) == 5
    why = {p["id"]: p["why"] for p in proposed}
    assert why[pages[0].id] == "your first page" and why[pages[-1].id] == "your last page"
    assert why[pages[7].id] == "the largest image" and why[pages[11].id] == "the smallest image"
    order = [p.id for p in pages]
    assert ids == sorted(ids, key=order.index)  # in the material's order


def test_samples_chosen_by_hand_hold_and_can_go_back(client, db, tmp_path):
    pages = _pages(db, tmp_path, 10)
    chosen = client.put("/api/recipes/samples", json={"ids": [pages[3].id, pages[4].id]}).json()
    assert chosen["chosen_by"] == "you" and [p["id"] for p in chosen["pages"]] == [pages[3].id, pages[4].id]
    assert client.get("/api/recipes/samples").json() == chosen
    back = client.put("/api/recipes/samples", json={"ids": []}).json()
    assert back["chosen_by"] == "fichero" and len(back["pages"]) == 5
    assert client.put("/api/recipes/samples", json={"ids": ["nope"]}).status_code == 422


# --- trying a stage -----------------------------------------------------------------------------------------------


def _set_up(client, purposes=("transcribe", "entities")):
    answers = {"purposes": list(purposes), "languages": ["es"], "scripts": ["Latn"], "materials": ["handwriting"]}
    recipe = client.post("/api/recipes/assemble", json=answers).json()
    assert client.put("/api/recipes/project", json={"answers": answers, "recipe": recipe}).status_code == 200


def _counts(db) -> dict[str, int]:
    return {m.__name__: len(db.all(m)) for m in (SegmentPass, ContentRepresentation, KnowledgeEntity)}


def test_names_is_tried_on_a_copy_of_the_samples_and_the_project_is_untouched(client, db, tmp_path, monkeypatch,
                                                                              jobs_run_by_the_test):
    from fichero_server.recipes import runner

    pages = _pages(db, tmp_path, 3)
    _set_up(client)
    before = _counts(db)
    library = Path(db.path).parent
    ran_in = []

    def fake_names_run(copy, card, documents, parent):
        """The names workflow, faked: it finds a person on the first page it is given, in the db it is given."""
        ran_in.append((Path(copy.path).parent, list(documents), card["steps"]))
        copy.save(KnowledgeEntity(canonical_name="Juan de la Cruz", entity_type="person"))
        return "thread-x", "done", None

    monkeypatch.setattr(runner, "_run_workflow", fake_names_run)
    started = client.post("/api/recipes/stages/names/try", json={})
    assert started.status_code == 200, started.text
    body = started.json()
    assert body["pages"] == [p.id for p in pages] and body["state"] == "waiting"
    job = jobs.read_job(db, body["job_id"])
    assert job["kind"] == samples.TRY_KIND

    samples.register_job_kinds()
    jobs.KINDS[samples.TRY_KIND].run(db, job["subject"])

    result = client.get("/api/recipes/stages/names/try").json()
    assert result["state"] == "done" and result["names"] == [{"name": "Juan de la Cruz", "type": "person"}]
    (where, documents, steps), = ran_in
    assert where.name == "names.fichero" and where.parent == library / "recipe" / "samples"
    assert set(documents).isdisjoint(p.id for p in pages)  # copies, never the project's pages
    assert not where.exists()  # the scratch copy is removed; the result is kept
    assert _counts(db) == before  # nothing written as the project's work


def test_read_is_tried_by_the_bake_off_one_evaluation_job(client, db, tmp_path, monkeypatch):
    from fichero_server.recipes import samples as s

    _set_up(client, ("transcribe",))
    started_with = {}

    def fake_start(db, library, a, cards, *, page_ids, volume, now, run_evaluation):
        started_with["page_ids"] = page_ids
        return {"id": "bk1", "job_id": "job-1"}

    monkeypatch.setattr("fichero_server.recipes.bakeoff.start", fake_start)
    # The samples hold the bake-off's corrected lines; without them Read is compared side by side instead (#5668).
    monkeypatch.setattr(s, "_bakeoff_ready", lambda db, page_ids: True)
    pages = _pages(db, tmp_path, 2)
    r = client.post("/api/recipes/stages/read/try", json={"page_ids": [pages[0].id]})
    assert r.status_code == 200, r.text
    assert r.json()["bakeoff"] == "bk1" and started_with["page_ids"] == [pages[0].id]
    assert json.loads((Path(db.path).parent / "recipe" / "samples" / "read.json").read_text())["bakeoff"] == "bk1"
    assert s.TRY_KIND not in {row["kind"] for row in jobs.find_jobs(db, kinds=[s.TRY_KIND])}


def test_a_cloud_stage_says_its_cost_and_runs_only_with_the_yes(client, db, tmp_path, monkeypatch):
    _set_up(client)
    _pages(db, tmp_path, 2)
    monkeypatch.setattr(samples, "_stage_plan", lambda db, stage, setup, n: {
        "refusals": [], "runs": [], "estimate": {"total_cost_usd": 0.12},
        "workflows": [{"steps": ["names"], "model_override": "gpt-x", "runs_on": "cloud:openai", "workflow": "W"}]})
    refused = client.post("/api/recipes/stages/names/try", json={})
    assert refused.status_code == 402 and "about $0.12" in refused.json()["detail"]
    assert client.post("/api/recipes/stages/names/try", json={"cost_ok": True}).status_code == 200


def test_a_stage_not_chosen_cannot_be_tried_and_unticking_clears_its_result(client, db, tmp_path):
    _set_up(client, ("transcribe",))
    _pages(db, tmp_path, 2)
    assert client.post("/api/recipes/stages/names/try", json={}).status_code == 422
    kept = Path(db.path).parent / "recipe" / "samples" / "names.json"
    kept.parent.mkdir(parents=True, exist_ok=True)
    kept.write_text(json.dumps({"stage": "names"}))
    assert client.get("/api/recipes/stages/names/try").status_code == 404
    assert not kept.exists()
