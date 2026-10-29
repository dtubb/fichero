"""A folder-scoped Start plan costs in proportion to the folder, not the library (#6268): an 832-page folder in a 61,000-page
library took 86 s. Counted in rows the plan reads from the database, not in time."""
from __future__ import annotations

from fichero_server.db import Database
from fichero_server.models import DocType, Document, FileType
from tests.unit.recipes.test_bakeoff_readers import _set_up


def _folder(db, name, pages):
    box = Document(name=name, doc_type=DocType.folder)
    db.save(box)
    for i in range(pages):
        db.save(Document(name=f"{name}-{i}.png", doc_type=DocType.file, file_type=FileType.image, path=f"/{name}/{i}.png",
                         parent_id=box.id))
    return box.id


def _read(db, monkeypatch, folder_id):
    """Rows hydrated: one plan for the folder asks of the database; asked once before, to warm what is kept."""
    from fichero_server.api.routes.system import recipes as routes

    routes._start_plan(db, folder_id, clusters=[])
    seen = [0]
    real = Database._hydrate_row

    def spy(self, *a, **k):
        seen[0] += 1
        return real(self, *a, **k)

    monkeypatch.setattr(Database, "_hydrate_row", spy)
    routes._start_plan(db, folder_id, clusters=[])
    monkeypatch.setattr(Database, "_hydrate_row", real)
    return seen


def test_the_plan_for_a_folder_reads_rows_in_proportion_to_the_folder(client, db, with_material, monkeypatch):
    _set_up(client)
    mine = _folder(db, "mine", 5)
    _folder(db, "others-small", 20)
    small = _read(db, monkeypatch, mine)
    _folder(db, "others-big", 200)
    big = _read(db, monkeypatch, mine)
    assert big[0] <= small[0] + 30, f"{big[0]} rows hydrated with 200 more pages elsewhere, {small[0]} before"
