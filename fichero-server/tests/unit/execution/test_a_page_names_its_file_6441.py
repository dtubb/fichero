"""A page node of a job tree names the multi-page file it belongs to (#6441, `activity.pane.one-outline-table`).

Spec: docs/contributor_manual/specs/ui/activity-pane.md: "a 120-page register [opens] to one file row that opens to its pages".
WHY: the pane makes one file row per `document_id`, so a register's 120 pages were 120 file rows; the tree did not say
which document a page is a page of. Through `GET /api/activity/jobs/{id}` over real job rows and documents.
"""
from __future__ import annotations

from fichero_server.execution import jobs
from fichero_server.models import DocType, Document, FileType


def test_a_page_of_a_multi_page_file_names_its_file_and_a_file_of_its_own_names_none(client, db):
    register = Document(name="register.pdf", doc_type=DocType.file, file_type=FileType.pdf)
    letter = Document(name="letter.png", doc_type=DocType.file, file_type=FileType.image)
    db.save(register)
    db.save(letter)
    pages = [Document(name=f"register p{n}", doc_type=DocType.page, file_type=FileType.pdf, parent_id=register.id, sequence=n)
             for n in (1, 2, 3)]
    for page in pages:
        db.save(page)
    jobs._ensure(db)
    run = jobs._insert(db, "workflow", "run-6441", None, "owner")
    step = jobs._insert(db, "workflow-step", "run-6441:read", None, "workflow")
    jobs.set_parent(db, step, run)
    for doc in [*pages, letter]:
        jobs.set_parent(db, jobs._insert(db, "read-a-page", doc.id, None, "workflow"), step)

    r = client.get(f"/api/activity/jobs/{run}")

    assert r.status_code == 200, r.text
    tree = r.json()
    leaves = {leaf["document_id"]: leaf for leaf in tree["children"][0]["children"]}
    for page in pages:
        assert (leaves[page.id]["file_id"], leaves[page.id]["file_name"]) == (register.id, "register.pdf")
    assert (leaves[letter.id]["file_id"], leaves[letter.id]["file_name"]) == (None, None), "a file of its own is its own file"
    assert (tree["file_id"], tree["children"][0]["file_id"]) == (None, None), "a run and a step are no page"
