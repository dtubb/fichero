"""Files dropped TOGETHER pair like their folder does (`POST /api/documents/import-batch`, 2026-09-28).

WHY: dropping the Ajami FOLDER paired each `.jpg` with its ALTO, but selecting the same jpg+xml
files and dropping them imported every `.xml` as a document of its own. The app uploads a drop
one file per request, and a request holding only the XML cannot know its image is in the next
one. The batch route takes the set at once and runs the SAME `plan_pairs`. If this regresses, a
drop of files gives raw-XML documents beside pages with no layout.

The layout file is kept as the page's source record (the pass's `original`), as a folder import
keeps it, and never becomes a document.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest

import fichero_server.api.main  # noqa: F401  (registers every action)
from fichero_server.models import Document, SegmentPass
from fichero_server.models.segments import Segment

FIXTURE = Path(__file__).resolve().parents[1] / "formats" / "fixtures" / "corpus" / "ajami_fulfulde_elit-wan-00130-001r.alto.xml"
AJAMI = Path.home() / "Fichero Test Corpus" / "Fulfulde in Arabic script (Ajami) - West African manuscript (right-to-left)"


def _jpeg() -> bytes:
    from PIL import Image

    out = io.BytesIO()
    Image.new("RGB", (300, 400), "white").save(out, format="JPEG")
    return out.getvalue()


def _drop(client, files: list[tuple[str, bytes]]):
    return client.post(
        "/api/documents/import-batch",
        files=[("files", (name, data, "application/octet-stream")) for name, data in files],
    )


def _live(db, model, **where):
    return [row for row in db.query(model, **where) if getattr(row, "deleted_at", None) is None]


def test_a_jpg_and_its_alto_dropped_together_are_one_page_with_its_pass(db, client):
    response = _drop(client, [
        ("ELIT_WAN_00130_001r.jpg", _jpeg()),
        ("ELIT_WAN_00130_001r.xml", FIXTURE.read_bytes()),   # states `...001r.JPG`: case-blind
    ])

    assert response.status_code == 200, response.text
    body = response.json()
    assert [d["name"] for d in body["documents"]] == ["ELIT_WAN_00130_001r.jpg"]
    assert body["imported_as_passes"] == ["ELIT_WAN_00130_001r.xml"], body
    assert not any(d.name.endswith(".xml") for d in db.all(Document))
    page_id = body["documents"][0]["id"]
    [imported] = [p for p in _live(db, SegmentPass, document_id=page_id) if p.import_file]
    assert imported.import_original                           # the file itself, kept
    assert any(s.kind == "line" for s in _live(db, Segment, pass_id=imported.id))


def test_an_xml_with_no_image_in_the_drop_is_an_ordinary_file_and_named(db, client):
    body = _drop(client, [("lonely.xml", FIXTURE.read_bytes()), ("other.jpg", _jpeg())]).json()

    assert sorted(d["name"] for d in body["documents"]) == ["lonely.xml", "other.jpg"]
    assert "lonely.xml" in body["unpaired"]


def test_two_files_of_one_name_are_refused_not_guessed(client):
    response = _drop(client, [("a.jpg", _jpeg()), ("A.JPG", _jpeg())])
    assert response.status_code == 422 and "same name" in response.json()["detail"]


def test_the_real_ajami_files_dropped_together_all_pair(db, client):
    """The folder Daniel dropped: 8 jpg + 8 ALTO, each stating `.JPG`. Local corpus only."""
    if not AJAMI.is_dir():
        pytest.skip("the Ajami folder is in the local corpus only")
    files = sorted(p for p in AJAMI.iterdir() if p.suffix.lower() in (".jpg", ".xml"))
    assert len(files) == 16

    body = _drop(client, [(p.name, p.read_bytes()) for p in files]).json()

    assert sorted(d["name"] for d in body["documents"]) == sorted(p.name for p in files if p.suffix == ".jpg")
    assert sorted(body["imported_as_passes"]) == sorted(p.name for p in files if p.suffix == ".xml")
    assert body["unpaired"] == {} and body["not_imported"] == {} and body["failed"] == {}


def test_the_real_ajami_folder_copied_and_dropped_pairs_every_file(db, tmp_path):
    """The same folder through the FOLDER route, as a copy in a temp dir. Local corpus only."""
    if not AJAMI.is_dir():
        pytest.skip("the Ajami folder is in the local corpus only")
    import shutil

    from fichero_server.actions.registry import ActionContext, registry

    folder = tmp_path / "ajami"
    shutil.copytree(AJAMI, folder)
    ctx = ActionContext(actor="historian", library_path=str(Path(db.path).parent), is_bootstrap=True)
    result = registry.invoke(db, "import.folder", {"path": str(folder)}, ctx).result

    assert len(result["interchange"]["imported_as_passes"]) == 8, result["interchange"]
    names = [db.get(Document, i).name for i in result["document_ids"] if db.get(Document, i)]
    assert names and not any(n.lower().endswith(".xml") for n in names)
