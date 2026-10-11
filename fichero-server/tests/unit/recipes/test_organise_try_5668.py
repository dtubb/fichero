"""Organise can be tried on sample pages (#5668, B's Organise review), tested to the spec:
`source.onboard.stages.organise-tried-on-a-run` (docs/contributor_manual/specs/source/models-chains-and-projects.md).

WHY: Organise's Try was refused ("cannot be tried on sample pages yet"), and the 3 to 5 samples spread across the
material could not have shown it anyway: where one document ends and the next begins is only seen on neighbouring
pages of one folder. Find the Documents runs for real on a copy; Split into entries' model is faked at its seam.
"""

from __future__ import annotations

from pathlib import Path

from fichero_server.execution import jobs
from fichero_server.models import Artifact, DocType, Document, FileType
from fichero_server.recipes import samples
from tests.unit.recipes.test_models_ux_5619 import ollama  # noqa: F401  (fixture: the person's Ollama, this Mac)

LETTERS = ["Muy señor mío: recibí la de vuestra merced del 3 de mayo.", "y quedo a su servicio.",
           "Dios guarde a vuestra merced muchos años. Madrid, 9 de mayo de 1702. Besa la mano de vuestra merced, "
           "Juan de la Cruz."]


def _folder(db, name: str, n: int) -> list[Document]:
    folder = Document(name=name, doc_type=DocType.folder)
    db.save(folder)
    pages = []
    for i in range(n):
        page = Document(name=f"{name} {i + 1:03d}", doc_type=DocType.file, file_type=FileType.image,
                        parent_id=folder.id, sequence=i + 1, page_content=LETTERS[i % 3])
        db.save(page)
        pages.append(page)
    return pages


def _organise_on(client, *, entries=False):
    """A project whose recipe has Organise: Find the Documents, and Split into entries (with the Ollama model the
    rules choose for it) when asked."""
    answers = {"purposes": ["transcribe"], "languages": ["es"], "scripts": ["Latn"], "materials": ["handwriting"]}
    jobs_asked = ["find-documents-in-a-folder"] + (["split-into-entries"] if entries else [])
    recipe = client.post("/api/recipes/assemble", json={**answers, "jobs": jobs_asked}).json()
    r = client.put("/api/recipes/project", json={"answers": answers, "recipe": recipe})
    assert r.status_code == 200, r.text


def test_organise_is_proposed_one_run_of_consecutive_pages_from_the_largest_folder(client, db):
    """"one run of consecutive pages … up to 12 in the folder's own order, from the folder with the most pages,
    starting at its first page, each saying why"."""
    _folder(db, "Small", 5)
    big = _folder(db, "Cartas", 30)
    body = client.get("/api/recipes/samples", params={"stage": "organise"}).json()
    assert [p["id"] for p in body["pages"]] == [p.id for p in big[:12]]
    assert body["pages"][0]["why"].startswith("page 1 of 12 in a row from “Cartas”")
    assert "where one document ends" in body["pages"][0]["why"]
    assert len(client.get("/api/recipes/samples").json()["pages"]) == 5  # the other stages keep their samples


def test_a_small_folder_is_its_own_run(db):
    pages = _folder(db, "Five", 5)
    assert [p["id"] for p in samples.propose_run(db)] == [p.id for p in pages]


def test_organise_is_tried_on_a_copy_and_its_documents_come_back_in_the_projects_ids(client, db, monkeypatch, ollama,
                                                                                     jobs_run_by_the_test):
    """"The try copies the run into a scratch project … runs Find the Documents there with nothing accepted by
    itself … and Split into entries with the step's model … The result … holds the documents proposed … in the
    project's own page ids … and the entries split from pages with text." The project is untouched."""
    from fichero_server.workflows.tools import diary_entries

    pages = _folder(db, "Cartas", 9)
    _organise_on(client, entries=True)
    library = Path(db.path).parent
    before = ({d.id for d in db.all(Document)}, {a.id for a in db.all(Artifact)})
    split_with = []

    async def fake_split(copy, with_text, config, **k):
        split_with.append((config.provider, config.model, len(with_text)))
        entry = Document(name="Entry 1", parent_id=with_text[0].id, page_content="Muy señor mío: recibí la de")
        copy.save(entry)
        return [entry], {"created": 1}, [], ["Entry 1"]

    monkeypatch.setattr(diary_entries, "split_pages_into_entries", fake_split)
    started = client.post("/api/recipes/stages/organise/try", json={})
    assert started.status_code == 200, started.text
    assert started.json()["pages"] == [p.id for p in pages]  # the run, not the scattered samples
    job = jobs.read_job(db, started.json()["job_id"])
    samples.register_job_kinds()
    jobs.KINDS[samples.TRY_KIND].run(db, job["subject"])

    result = client.get("/api/recipes/stages/organise/try").json()
    assert result["state"] == "done", result
    assert result["documents"], result
    proposed = [i for d in result["documents"] for i in d["page_ids"]]
    assert set(proposed) <= {p.id for p in pages}  # the project's ids, never the copy's
    assert set(result["documents"][0]) == {"page_ids", "name", "kind", "confidence", "reasons"}
    assert split_with == [("ollama", "llama3.2:latest", 9)], result["ran"]
    assert result["entries"] == [{"page_id": pages[0].id, "name": "Entry 1", "opening": "Muy señor mío: recibí la de"}]
    assert (library / "recipe" / "samples" / "organise.json").exists()
    assert not (library / "recipe" / "samples" / "organise.fichero").exists()
    # No group, no entry, no stored proposal: nothing written as the project's work.
    assert ({d.id for d in db.all(Document)}, {a.id for a in db.all(Artifact)}) == before


def test_the_person_may_choose_the_pages_organise_is_tried_on(client, db):
    pages = _folder(db, "Cartas", 20)
    _organise_on(client)
    picked = [p.id for p in pages[5:9]]
    r = client.post("/api/recipes/stages/organise/try", json={"page_ids": picked})
    assert r.status_code == 200, r.text
    assert r.json()["pages"] == picked
