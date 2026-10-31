"""#6295: Start with `first_pages` queues a run on those pages alone (Finder order), and its answer describes that run, not the
whole project (the screen right after Start showed the whole project's pages and a cap refusal for a run that had started)."""
# ruff: noqa: F811 -- pytest fixtures imported from the sibling tests are named as test arguments
from __future__ import annotations

from tests.unit.recipes.test_recipe_execution_to_spec import (  # noqa: F401  (fixtures)
    _finished,
    _recipe,
    _runs,
    _save,
    engine,
    pages,
)
from tests.unit.recipes.test_step_rerun_on_folder import STEPS


def test_start_on_the_first_pages_runs_them_and_answers_for_them(client, db, pages, tmp_path, engine):
    _save(client, _recipe(tmp_path, *STEPS))
    whole = client.get("/api/recipes/project/start").json()
    assert whole["estimate"]["pages"] == 2

    r = client.post("/api/recipes/project/start", json={"first_pages": 1})
    assert r.status_code == 200, r.text
    answer = r.json()
    assert answer["estimate"]["pages"] == 1, "the answer is for the one page queued, not the project's two"
    assert answer["cloud_cap"]["pages"] == 1
    assert _finished(client, answer["started"]["job_id"])["state"] == "done"
    assert engine.read == ["p0.png"], "the first page in Finder order, and only it"
    assert len(_runs(client)) == 1


def test_start_takes_the_first_pages_or_a_folder_or_some_pages_not_two(client, db, pages, tmp_path, engine):
    _save(client, _recipe(tmp_path, *STEPS))
    both = client.post("/api/recipes/project/start", json={"first_pages": 1, "documents": [pages[0].id]})
    assert both.status_code == 422 and "one of them" in both.text
    assert client.post("/api/recipes/project/start", json={"first_pages": 0}).status_code == 422


def test_a_run_on_the_first_pages_reads_the_pages_the_plan_counted_not_their_entries(db):
    """The run expands the pages it is given (a photograph cut since is its pages): a page holding diary entries became its
    entries, so the run read pages the plan's N did not count. An entry is not a page to read, as `unit_of_work_ids` has it."""
    from fichero_server.models import DocType, Document
    from fichero_server.recipes.cloud_cap import first_pages_of
    from fichero_server.recipes.done import pages_for

    page = Document(name="p1", doc_type=DocType.page)
    db.save(page)
    db.save(Document(name="e1", doc_type=DocType.page, node_kind="entry", parent_id=page.id))
    other = Document(name="p2", doc_type=DocType.page)
    db.save(other)
    first = first_pages_of(db, 2)
    assert set(first) == {page.id, other.id}
    assert set(pages_for(db, {}, first)) == set(first), "the run's pages are the plan's pages"


def test_the_first_pages_take_a_cut_photograph_whole_as_the_run_reads_it(db):
    """The run batches a page cut from a photograph as its photograph and reads every cut. The plan's N counted only the first
    cuts: a run on N pages that stopped inside a photograph read more than the plan priced. The first pages end at the
    photograph's last cut, and the plan counts those."""
    from fichero_server.models import DocType, Document, FileType
    from fichero_server.recipes.cloud_cap import first_pages_of
    from fichero_server.recipes.done import material

    plain = Document(name="A", doc_type=DocType.file, file_type=FileType.image, path="/x/a")
    photo = Document(name="B", doc_type=DocType.file, file_type=FileType.image, path="/x/b")
    db.save(plain)
    db.save(photo)
    cuts = []
    for i in range(3):
        cut = Document(name=f"B-{i}", doc_type=DocType.chunk, parent_id=photo.id, sequence=i,
                       metadata={"split_source_id": photo.id})
        db.save(cut)
        cuts.append(cut.id)
    # pages in Finder order: A, then the three cuts of B; N = 2 stops after the first cut
    first = first_pages_of(db, 2)
    assert first[0] == plain.id and set(first[1:]) == set(cuts), "B's cuts go together: the run reads them as one photograph"
    assert material(db, set(first))["pages"] == 4, "and the plan counts what the run reads"
    assert first_pages_of(db, 1) == [plain.id], "a first page before the photograph is just that page"
