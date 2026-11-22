"""Files of one name dropped together all import (#6831, #4579).

Spec: docs/contributor_manual/specs/importer/importer.md -- `importer.same-name.files-from-different-folders-both-import`.
Driven through `POST /api/documents/import-batch`, the route a remote client, the command line and the soak script use.
A layout file that could belong to two images of one name pairs with neither and is listed as unpaired with that reason.
"""
from __future__ import annotations

import io
from pathlib import Path

import fichero_server.api.main  # noqa: F401  (registers every action)
from fichero_server.models import Document, SegmentPass

ALTO = Path(__file__).resolve().parents[1] / "formats" / "fixtures" / "corpus" / "ajami_fulfulde_elit-wan-00130-001r.alto.xml"


def _jpeg(shade: int) -> bytes:
    from PIL import Image

    out = io.BytesIO()
    Image.new("RGB", (300, 400), (shade, shade, shade)).save(out, format="JPEG")
    return out.getvalue()


def _drop(client, files: list[tuple[str, bytes]]):
    return client.post(
        "/api/documents/import-batch",
        files=[("files", (name, data, "application/octet-stream")) for name, data in files],
    )


def test_two_uploads_of_one_name_make_two_pages(db, client):
    response = _drop(client, [("IMG_0001.jpg", _jpeg(10)), ("IMG_0001.jpg", _jpeg(200)), ("IMG_0002.jpg", _jpeg(90))])

    assert response.status_code == 200, response.text
    body = response.json()
    assert sorted(d["name"] for d in body["documents"]) == ["IMG_0001.jpg", "IMG_0001.jpg", "IMG_0002.jpg"]
    assert len({d["id"] for d in body["documents"]}) == 3
    assert body["failed"] == {}
    assert sorted(d.name for d in db.all(Document) if d.name.startswith("IMG_")) == ["IMG_0001.jpg", "IMG_0001.jpg", "IMG_0002.jpg"]


def test_names_that_differ_only_in_case_both_import(db, client):
    body = _drop(client, [("a.jpg", _jpeg(10)), ("A.JPG", _jpeg(200))]).json()
    assert sorted(d["name"] for d in body["documents"]) == ["A.JPG", "a.jpg"]


def test_two_images_of_one_name_and_a_layout_file_of_that_name_are_two_pages_and_one_unpaired_entry(db, client):
    body = _drop(client, [
        ("ELIT_WAN_00130_001r.jpg", _jpeg(10)),
        ("ELIT_WAN_00130_001r.jpg", _jpeg(200)),
        ("ELIT_WAN_00130_001r.xml", ALTO.read_bytes()),
    ]).json()

    names = sorted(d["name"] for d in body["documents"])
    assert names == ["ELIT_WAN_00130_001r.jpg", "ELIT_WAN_00130_001r.jpg", "ELIT_WAN_00130_001r.xml"], names
    assert body["imported_as_passes"] == []
    assert list(body["unpaired"]) == ["ELIT_WAN_00130_001r.xml"]
    assert "2 images" in body["unpaired"]["ELIT_WAN_00130_001r.xml"]
    image_ids = {d["id"] for d in body["documents"] if d["name"].endswith(".jpg")}
    assert not [p for p in db.all(SegmentPass) if p.document_id in image_ids]


def test_a_layout_file_beside_one_image_of_its_name_still_pairs(db, client):
    body = _drop(client, [("ELIT_WAN_00130_001r.jpg", _jpeg(10)), ("ELIT_WAN_00130_001r.xml", ALTO.read_bytes()),
                          ("x.jpg", _jpeg(50)), ("x.jpg", _jpeg(60))]).json()
    assert body["imported_as_passes"] == ["ELIT_WAN_00130_001r.xml"]
    assert body["unpaired"] == {}
