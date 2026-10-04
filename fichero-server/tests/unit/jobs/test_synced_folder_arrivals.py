"""The synced folder, files arriving: new images, layout beside them, renamed files (#4952).

Spec: docs/contributor_manual/specs/source/synced-folder.md, "In, as they arrive". Written from the
spec's behaviours before the code, and driven through the public surface: a folder is tied with
`POST /api/sync-folders`, intake is switched on with `PUT /api/sync-folders/{id}/intake`, files are
put into the folder as another program would (while the engine runs: the folder is watched), and
the folder is followed with `GET /api/sync-folders`. Documents and passes are read from the
database: no route lists a page's passes yet.

Not covered here because not built yet: running the recipe of the subfolder a file lands in (an
image runs the project's automatic work, as any import does), out-only formats.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from tests.unit.jobs.test_adopted_folder import FIXTURES
from tests.unit.jobs.test_synced_folder import _status, _tie, _wait_for, _written, page  # noqa: F401


@pytest.fixture(autouse=True)
def quick(monkeypatch, db):
    from fichero_server import sync_folder

    monkeypatch.setattr(sync_folder, "QUIET_SECONDS", 0.3)
    monkeypatch.setattr(type(db), "embed", lambda self, doc, *a, **k: True)


def _image(path: Path, size=(864, 300)) -> Path:
    from PIL import Image

    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, "white").save(path)
    return path


def _documents_named(db, name):
    from fichero_server.models import Document

    return [d for d in db.all(Document) if d.name == name and d.deleted_at is None]


def _passes(db, document_id):
    from fichero_server.models.segments import SegmentPass

    return [p for p in db.all(SegmentPass) if p.document_id == document_id]


def _intake_on(client, folder_id):
    """Switch intake on, and wait out the read that switching it on makes: what arrives after is
    found only by watching the folder."""
    r = client.put(f"/api/sync-folders/{folder_id}/intake", json={"on": True})
    assert r.status_code == 200, r.text
    # The read is queued before the switch returns; Activity lists only work not yet finished.
    assert _wait_for(lambda: not any(j["task_type"] == "read-from-folder" for j in _jobs(client)))


def _jobs(client):
    return client.get("/api/activity/jobs").json()["jobs"]


@pytest.fixture
def edition(client, page, tmp_path):
    """A made folder, written, with intake on."""
    folder = tmp_path / "edition"
    folder_id = _tie(client, folder, ["pagexml"])
    assert _written(client, folder_id, 1)
    _intake_on(client, folder_id)
    return folder, folder_id


def test_source_sync_new_images_come_in__an_image_put_in_the_folder_becomes_a_source(client, db, edition):
    """Behaviour `source.sync.new-images-come-in`: "images added to the folder become sources and run
    the recipe of the folder they land in." With the engine running, an image put into the folder
    becomes a page of the project, its file left where it was put: found by watching the folder,
    with nothing else asking for it to be read."""
    folder, folder_id = edition
    image = _image(folder / "incoming" / "letter-1.png")
    assert _wait_for(lambda: len(_documents_named(db, "letter-1.png")) == 1)
    [doc] = _documents_named(db, "letter-1.png")
    assert Path(doc.path).resolve() == image.resolve() and image.exists()
    assert _wait_for(lambda: "incoming/letter-1.png" in _status(client, folder_id)["taken_in"])


def test_source_sync_one_import_path__an_image_and_its_page_xml_arrive_as_a_folder_import_would(client, db, edition):
    """Behaviour `source.sync.one-import-path`: "files arriving through the synced folder go through
    the same import path as any other import." An image with its PAGE XML beside it becomes a page
    with that file as its pass, the pairing a folder import makes, and the XML is not a document."""
    folder, _folder_id = edition
    (folder / "incoming").mkdir()
    (folder / "incoming" / "letter-2.xml").write_bytes(
        (FIXTURES / "escriptorium_export.page.xml").read_bytes()
        .replace(b"default.png", b"letter-2.png").replace(b'imageHeight="206"', b'imageHeight="300"'))
    _image(folder / "incoming" / "letter-2.png")
    assert _wait_for(lambda: len(_documents_named(db, "letter-2.png")) == 1
                     and len(_passes(db, _documents_named(db, "letter-2.png")[0].id)) == 1)
    [doc] = _documents_named(db, "letter-2.png")
    assert _passes(db, doc.id)[0].import_file == "letter-2.xml"
    assert _documents_named(db, "letter-2.xml") == []


def test_source_sync_files_carry_ids__a_renamed_file_is_still_matched_to_its_source(client, db, page, edition):
    """Behaviour `source.sync.files-carry-ids`: "each written file carries its source's lasting id, so
    a renamed or moved file is still matched to its source." A written file renamed and then edited
    in the folder comes in as a pass on its page, and the folder knows it by its new name."""
    folder, folder_id = edition
    before = len(_passes(db, page.id))
    old = folder / "pagexml" / f"book-p1--{page.id}.page.xml"
    new = folder / "pagexml" / "renamed by hand.page.xml"
    old.rename(new)
    new.write_text(new.read_text(encoding="utf-8").replace("</PcGts>", "<!-- edited in Oxygen --></PcGts>"),
                   encoding="utf-8")
    assert _wait_for(lambda: len(_passes(db, page.id)) == before + 1)
    status = _status(client, folder_id)
    assert "pagexml/renamed by hand.page.xml" in status["files"]
    assert status["deleted_outside"] == [] and status["taken_in"] == []


def test_source_sync_read_back_formats__a_file_of_another_kind_is_listed_not_read(client, db, edition):
    """Behaviour `source.sync.read-back-formats`: "only files in a format Fichero can import (PAGE,
    ALTO, TEI) are read back; a change to any other file is listed as 'changed outside; not read
    back'." A note put in the folder becomes nothing in the project, and is listed."""
    folder, folder_id = edition
    (folder / "notes.md").write_text("# what I changed\n", encoding="utf-8")
    assert _wait_for(lambda: _status(client, folder_id)["not_read_back"] == ["notes.md"])
    assert _documents_named(db, "notes.md") == []


def test_source_sync_intake_is_opt_in__the_preview_counts_new_images_by_kind(client, db, page, tmp_path):
    """Behaviour `source.sync.intake-is-opt-in`: the preview "shows what it will bring in (counts by
    kind)": with intake off, two images put in the folder are counted and nothing comes in."""
    folder = tmp_path / "edition"
    folder_id = _tie(client, folder, ["pagexml"])
    assert _written(client, folder_id, 1)
    _image(folder / "a.png")
    _image(folder / "b.jpg")
    preview = client.get(f"/api/sync-folders/{folder_id}/intake").json()
    assert preview == {"on": False, "would_bring_in": {"images": 2}}
    assert _documents_named(db, "a.png") == []
