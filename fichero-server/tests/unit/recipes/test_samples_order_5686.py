"""Sample pages follow the folder's own order, and only Organise gets a run of them (#5686), tested to the spec:
`source.onboard.stages.samples-proposed` and `source.onboard.stages.organise-tried-on-a-run`
(docs/contributor_manual/specs/source/models-chains-and-projects.md).

WHY: the overnight MCP walk (2026-10-11): Find Regions was offered Organise's run; the run was `10_`, `11_` … `19_`,
`1_`, `20_` (names sorted as strings); Read's "your first page" was `39_Hoja_549_Recto`, the order the import
happened to create the pages in.
"""

from __future__ import annotations

import random

from fichero_server.models import DocType, Document, FileType
from fichero_server.recipes import samples


def _folder_imported_out_of_order(db, n: int = 25) -> list[Document]:
    folder = Document(name="CACIQUES", doc_type=DocType.folder)
    db.save(folder)
    names = [f"{i}_Hoja_{529 + i}_Recto.JPG" for i in range(1, n + 1)]
    pages = {}
    for name in random.Random(5686).sample(names, len(names)):  # created in the import's own order
        page = Document(name=name, doc_type=DocType.file, file_type=FileType.image, parent_id=folder.id)
        db.save(page)
        pages[name] = page
    return [pages[name] for name in names]  # as Items shows them


def test_organises_run_is_the_folders_first_pages_in_its_natural_order(db):
    pages = _folder_imported_out_of_order(db)
    assert [p["id"] for p in samples.propose_run(db)] == [p.id for p in pages[:12]]


def test_the_first_and_last_samples_are_the_folders_first_and_last_pages(db):
    pages = _folder_imported_out_of_order(db)
    proposed = {p["why"]: p["id"] for p in samples.propose(db)}
    assert proposed["your first page"] == pages[0].id
    assert proposed["your last page"] == pages[-1].id


def test_find_regions_gets_the_spread_samples_not_organises_run(db):
    _folder_imported_out_of_order(db)
    assert samples.chosen(db, "find-regions") == samples.chosen(db)
    assert samples.chosen(db, "organise")["pages"] != samples.chosen(db)["pages"]
