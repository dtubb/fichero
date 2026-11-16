"""`GET /api/pages/{id}/image-chain` (`wide.chain.served-by-the-engine`, #6296, #5386): the page's current image, the renditions
in the order they were made with their operation's name and figure in words, which one every later step reads, and each
rendition passed over with its reason. The same answer Preview's rendition axis reads (`media/rendition_order.py`).

Real pixels and the real Prepare Images step: the chain is read back from what `page_crop` wrote, never from a fixture of it.
"""
from __future__ import annotations

from PIL import Image

from fichero_server.models import DocType, Document, FileType, ImageEditChain, NodeRegion, Rendition
import fichero_server.api.routes.document.renditions  # noqa: F401
from tests.unit.media.test_turn_straighten_blank import _lines_of, _ruled


def _photograph(db, tmp_path, name="photo.png") -> Document:
    path = tmp_path / name
    Image.new("RGB", (200, 100), "white").save(path)
    doc = Document(name=name, doc_type=DocType.file, file_type=FileType.image, path=str(path), metadata={})
    db.save(doc)
    return doc


def _chain(client, doc):
    r = client.get(f"/api/pages/{doc.id}/image-chain")
    assert r.status_code == 200, r.text
    return r.json()


def test_a_page_with_no_renditions_is_the_photograph_alone_and_it_is_what_is_read(client, db, tmp_path):
    doc = _photograph(db, tmp_path)
    body = _chain(client, doc)
    assert body["page_id"] == doc.id and body["read_from"] == "original"
    (only,) = body["steps"]
    assert only["kind"] == "photograph" and only["reads_this"] is True and only["rendition_id"] is None
    assert body["passed_over"] == []


def test_the_chain_after_a_real_prepare_run_is_in_the_order_made_with_words_and_one_reads_this(client, db, tmp_path, monkeypatch):
    from fichero_server.media import find_page as module
    from fichero_server.media import turn_by_text as turn_module
    from fichero_server.recipes.page_crop import crop_pages

    monkeypatch.setattr(module, "find_page_vision", lambda image: None)
    monkeypatch.setattr(turn_module, "read_lines", lambda image, db_path=None: _lines_of(180))
    table = Image.new("RGB", (1400, 1100), (14, 12, 10))
    table.paste(_ruled(2.0).resize((900, 700)), (250, 200))
    path = tmp_path / "table.png"
    table.save(path)
    doc = Document(name=path.name, doc_type=DocType.file, file_type=FileType.image, path=str(path), metadata={})
    db.save(doc)
    crop_pages(db, [doc.id], "run-1", prepare=True)

    body = _chain(client, doc)

    steps = body["steps"]
    roles = [s["role"] for s in steps]
    assert roles[0] == "original" and steps[0]["kind"] == "photograph"
    assert roles[1] == "crop" and "rotated" in roles and roles.index("crop") < roles.index("rotated"), roles
    assert body["read_from"] == "rendition" and [s["reads_this"] for s in steps].count(True) == 1
    assert steps[-1]["reads_this"] is True, "the newest rendition is the one every later step reads"
    by_role = {s["role"]: s for s in steps}
    assert by_role["crop"]["operation"] == "Crop to the paper"
    assert by_role["rotated"]["operation"] == "Straighten" and by_role["rotated"]["figure"] == "turned 180° from its text"
    assert all(s["figure"] for s in steps[1:]) and all(s["rendition_id"] for s in steps[1:])
    # the renditions' bytes are served at the existing content route, by the id the chain names
    assert client.get(f"/api/documents/{doc.id}/renditions/{by_role['rotated']['rendition_id']}/content").status_code == 200
    # Preview's axis reads the same ordering: the engine's own `order_renditions`, ids only
    listed = [i["id"] for i in client.get(f"/api/documents/{doc.id}/renditions").json()["items"]]
    assert body["axis"] == listed


def test_the_figures_in_words_come_from_the_rows_transform_and_note(client, db, tmp_path):
    doc = _photograph(db, tmp_path)
    for role, transform, note in (
        ("squared", {"method": "square"}, "the page squared from its four corners"),
        ("flattened", {"method": "flatten"}, "the page flattened toward its gutter"),
        ("deskewed", {"method": "straighten", "angle": -1.3}, "straightened 1.30 degrees"),
        ("prepared", None, "contrast raised"),
    ):
        picture = tmp_path / f"{role}.png"
        Image.new("RGB", (200, 100), "white").save(picture)
        db.save(Rendition(document_id=doc.id, role=role, path=str(picture), note=note, pixel_width=200, pixel_height=100,
                          transform=NodeRegion(rect=[0, 0, 1, 1], **transform) if transform else None))
    by_role = {s["role"]: s for s in _chain(client, doc)["steps"]}
    assert by_role["squared"]["figure"] == "squared from its corners" and by_role["squared"]["operation"] == "Crop to the paper"
    assert by_role["flattened"]["figure"] == "flattened toward the gutter"
    assert by_role["deskewed"]["figure"] == "straightened 1.3°" and by_role["deskewed"]["operation"] == "Straighten"
    assert by_role["prepared"]["figure"] == "contrast raised" and by_role["prepared"]["operation"] == "Clarity"


def test_a_rendition_passed_over_says_why_and_the_one_before_it_is_read(client, db, tmp_path):
    doc = _photograph(db, tmp_path)
    cut = tmp_path / "crop.png"
    Image.open(doc.path).crop((20, 10, 140, 90)).save(cut)
    db.save(Rendition(document_id=doc.id, role="crop", path=str(cut), pixel_width=120, pixel_height=80,
                      transform=NodeRegion(rect=[0.1, 0.1, 0.6, 0.8])))
    flat = tmp_path / "flat.png"
    Image.new("RGB", (120, 80), "white").save(flat)
    db.save(Rendition(document_id=doc.id, role="flattened", path=str(flat), pixel_width=120, pixel_height=80,
                      transform=NodeRegion(rect=[0, 0, 1, 1], method="flatten")))

    body = _chain(client, doc)

    assert body["read_from"] == "rendition"
    by_role = {s["role"]: s for s in body["steps"]}
    assert by_role["crop"]["reads_this"] is True and by_role["flattened"]["reads_this"] is False
    (passed,) = body["passed_over"]
    assert passed["role"] == "flattened" and passed["rendition_id"] == by_role["flattened"]["rendition_id"]
    assert "flattened page" in passed["why"], passed
    assert by_role["flattened"]["passed_over"] == passed["why"]


def test_a_person_edit_is_what_is_read_and_no_rendition_reads_this(client, db, tmp_path):
    doc = _photograph(db, tmp_path)
    cut = tmp_path / "crop.png"
    Image.open(doc.path).crop((20, 10, 140, 90)).save(cut)
    db.save(Rendition(document_id=doc.id, role="crop", path=str(cut), transform=NodeRegion(rect=[0.1, 0.1, 0.6, 0.8])))
    db.save(ImageEditChain(document_id=doc.id, operations=[{"op": "crop", "page": 1, "params":
                                                          {"left": 20, "top": 10, "width": 120, "height": 80}}]))
    body = _chain(client, doc)
    assert body["read_from"] == "edited" and not any(s["reads_this"] for s in body["steps"])


def test_a_missing_page_is_404(client):
    assert client.get("/api/pages/nope/image-chain").status_code == 404
