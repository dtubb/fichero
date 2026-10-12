"""A folder's pages are in one order on every surface (#5693), tested to the spec:
`source.onboard.stages.samples-proposed` (docs/contributor_manual/specs/source/models-chains-and-projects.md).

WHY: Find the Documents ordered the pages as strings (`10_`, `11_` … `1_`, `20_`), and the training set and a remote
read sorted the names as strings too; Items read them naturally. One shared key now orders all of them.
"""

from __future__ import annotations

from fichero_server.api.routes.document.documents import _ordered_by_sort_order
from fichero_server.core.naturalsort import in_folder_order
from fichero_server.finddocs import job as finddocs_job
from fichero_server.recipes import samples
from tests.unit.recipes.test_samples_order_5686 import _folder_imported_out_of_order


def test_every_surface_orders_a_folders_pages_alike(db):
    pages = _folder_imported_out_of_order(db, n=21)
    natural = [p.id for p in pages]
    shuffled = list(reversed(pages))
    assert [d.id for d in finddocs_job._ordered(shuffled)] == natural
    assert [d.id for d in _ordered_by_sort_order(shuffled)] == natural
    assert [d.id for d in samples._pages(db)] == natural
    assert [d.id for d in sorted(shuffled, key=in_folder_order)] == natural


def test_an_order_a_person_set_and_a_pages_place_in_its_file_come_before_the_name(db):
    pages = _folder_imported_out_of_order(db, n=3)
    pages[0].sort_order = 5
    assert sorted(pages, key=in_folder_order)[-1].id == pages[0].id
    pages[0].sort_order = 0
    pages[2].sequence, pages[1].sequence = 1, 2
    assert [d.id for d in sorted(pages, key=in_folder_order)] == [pages[2].id, pages[1].id, pages[0].id]


def test_the_training_set_and_a_remote_read_name_the_shared_order():
    from pathlib import Path

    src = Path(__file__).parents[3] / "src/fichero_server"
    for path in ("training/kraken_set.py", "remote_read/package.py", "api/routes/document/inspector.py"):
        assert "key=in_folder_order" in (src / path).read_text(encoding="utf-8"), path
