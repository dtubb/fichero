"""Material that is already text is not read (#5553), tested to the spec
(docs/contributor_manual/specs/source/models-chains-and-projects.md, `source.recipe.text-material-is-not-read`).

Through the public surface: `POST /api/recipes/assemble` (with the answer, and unset on the open project's sample),
`POST /api/recipes/check`, `PUT /api/recipes/project` and the Start plan.
"""
from __future__ import annotations

from fichero_server.models import Artifact
from tests.unit.recipes.test_recipe_execution_to_spec import engine, pages  # noqa: F401  (fixtures)

PICTURE_JOBS = {"split-pages", "prepare-the-image", "find-regions", "find-lines", "read-a-line", "read-a-page",
                "correct", "tie-text-to-lines", "train-a-model"}


def _assemble(client, **answers):
    body = {"languages": ["en"], "scripts": ["Latn"], "mac_memory_gb": 16, **answers}
    r = client.post("/api/recipes/assemble", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def _jobs(recipe) -> list[str]:
    return [s["job"] for s in recipe["steps"]]


def test_text_material_gets_no_reading_step_and_starts_at_search(client):
    """"material that is already text [...] gets no reading step: the plan goes straight to search and whatever else
    was ticked, and Ready says the notes are already text": no lines, readers or corrections, not even training at
    10,000 pages; the recipe passes the check, because text is what it starts from."""
    recipe = _assemble(client, purposes=["search", "entities"], materials=["text"], pages=10_000)
    assert not PICTURE_JOBS & set(_jobs(recipe)), _jobs(recipe)
    assert _jobs(recipe) == ["find-names-tag-words", "make-a-vector"]
    assert recipe["problems"] == [] and recipe["gaps"] == []
    assert recipe["already_text"].startswith("The material is already text: nothing to read")
    assert recipe["suits"]["material"] == ["text"]
    r = client.post("/api/recipes/check", json={"recipe": recipe})
    assert r.status_code == 200 and r.json()["problems"] == []


def test_read_material_still_reads_and_a_mix_reads_only_what_needs_reading(client):
    """Handwriting is read as before; handwriting beside text gets readers for the handwriting only."""
    hand = _assemble(client, purposes=["search"], materials=["handwriting"])
    assert {"find-lines", "read-a-line"} <= set(_jobs(hand)) and hand.get("already_text") is None
    mixed = _assemble(client, purposes=["search"], materials=["handwriting", "print", "text"])
    read = next(s for s in mixed["steps"] if s["job"] == "read-a-line")
    assert [r["material"] for r in read["readers"]] == ["handwriting", "print"]
    assert mixed.get("already_text") is None


def test_the_check_refuses_text_jobs_without_text(client):
    """The check's start follows the material: a recipe of search alone on handwriting needs a reading step first."""
    steps = [{"id": "search", "job": "make-a-vector"}]
    base = {"fichero_recipe": 1, "id": "t", "version": "0.1.0", "title": "t", "steps": steps}
    on_text = client.post("/api/recipes/check", json={"recipe": {**base, "suits": {"material": ["text"]}}}).json()
    on_hand = client.post("/api/recipes/check", json={"recipe": {**base, "suits": {"material": ["handwriting"]}}}).json()
    assert on_text["problems"] == []
    assert any("no earlier step gives" in p for p in on_hand["problems"])


def test_unset_material_is_text_when_the_sample_is_text(client, db, pages):
    """Unset, the material is read off the open project's sample: photographs are read; once every page in the
    sample is a note or a PDF page with a text layer, nothing is; an answer still overrides it."""
    from fichero_server.importers.ingest import PDF_TEXT_GEOMETRY_ARTIFACT
    from fichero_server.models import FileType

    assert "read-a-line" in _jobs(_assemble(client, purposes=["search"]))
    note, pdf_page = pages
    note.file_type = FileType.text
    db.save(note)
    # A scanned PDF page: its text-layer artifact says there is no layer (zero boxes), so it is still read.
    pdf_page.file_type = None
    db.save(pdf_page)
    db.save(Artifact(document_id=pdf_page.id, artifact_type=PDF_TEXT_GEOMETRY_ARTIFACT, content="",
                     data={"box_count": 0}, provider="pymupdf"))
    assert "read-a-line" in _jobs(_assemble(client, purposes=["search"]))
    db.save(Artifact(document_id=pdf_page.id, artifact_type=PDF_TEXT_GEOMETRY_ARTIFACT, content="Dear Sir",
                     data={"box_count": 2}, provider="pymupdf"))
    unset = _assemble(client, purposes=["search"])
    assert _jobs(unset) == ["make-a-vector"] and unset["already_text"]
    assert "read-a-line" in _jobs(_assemble(client, purposes=["search"], materials=["print"]))


def test_a_saved_text_project_plans_with_no_refusal(client, pages):
    """Saved and planned, the text recipe's Start plan refuses nothing for want of a reading step."""
    recipe = _assemble(client, purposes=["search"], materials=["text"])
    r = client.put("/api/recipes/project", json={"answers": {"purposes": ["search"], "materials": ["text"],
                                                             "languages": ["en"], "scripts": ["Latn"]},
                                                 "recipe": recipe})
    assert r.status_code == 200, r.text
    plan = client.get("/api/recipes/project/start")
    assert plan.status_code == 200, plan.text
    assert not [x for x in plan.json().get("refusals", []) if "no earlier step gives" in x], plan.json()
