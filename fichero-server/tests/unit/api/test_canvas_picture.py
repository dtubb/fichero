"""GET /api/canvas/folders/{id}/canvas-picture: the board as one PNG (#5568).

An agent organising a project through the MCP must be able to LOOK at a folder's canvas. These
tests read the picture back as pixels: a placed page's stored thumbnail at its saved position, a
group's outline, the "not placed" strip, and the size bound.
"""

from __future__ import annotations

import io

from PIL import Image

from fichero_server.models import DocType, Document

BASE = "/api/canvas/folders"
RED = (220, 20, 20)


def _doc(db, doc_id: str, parent_id: str, **extra) -> Document:
    doc = Document(id=doc_id, name=doc_id, parent_id=parent_id, doc_type=extra.pop("doc_type", DocType.file), **extra)
    db.save(doc)
    return doc


def _red_thumbnails(monkeypatch, tmp_path, ids: set[str]) -> None:
    """Every doc in `ids` has a stored, solid-red thumbnail; the rest have none."""
    path = tmp_path / "red.jpg"
    Image.new("RGB", (60, 80), RED).save(path)
    from fichero_server.db import storage

    monkeypatch.setattr(storage, "get_thumbnail", lambda doc, package_path=None, db=None: path if doc.id in ids else None)


def _picture(client, folder: str, **params) -> Image.Image:
    response = client.get(f"{BASE}/{folder}/canvas-picture", params=params)
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "image/png"
    return Image.open(io.BytesIO(response.content)).convert("RGB")


def _is_red(pixel) -> bool:
    return pixel[0] > 180 and pixel[1] < 80 and pixel[2] < 80


def test_a_placed_page_shows_its_thumbnail_at_its_saved_position(client, db, monkeypatch, tmp_path):
    """WHY: the picture is only useful if what is drawn where is what the layout says."""
    _doc(db, "folder-P", None, doc_type=DocType.folder)
    _doc(db, "page-1", "folder-P")
    _red_thumbnails(monkeypatch, tmp_path, {"page-1"})
    saved = client.put(f"{BASE}/folder-P/canvas-layout", json={"items": [{"item_id": "page-1", "x": 0, "y": 0}]})
    assert saved.status_code == 200, saved.text

    picture = _picture(client, "folder-P")
    # One 120x150 card centred at (0, 0), a 60-unit margin, fitted at scale 2: its centre is (240, 270).
    assert picture.size == (480, 600)
    assert _is_red(picture.getpixel((240, 270)))
    assert not _is_red(picture.getpixel((10, 10))), "the margin is background"


def test_a_page_moved_on_the_board_moves_in_the_picture(client, db, monkeypatch, tmp_path):
    """WHY: lay out, look, adjust: a saved move must show in the next look."""
    _doc(db, "folder-M", None, doc_type=DocType.folder)
    _doc(db, "page-a", "folder-M")
    _doc(db, "page-b", "folder-M")
    _red_thumbnails(monkeypatch, tmp_path, {"page-b"})
    client.put(f"{BASE}/folder-M/canvas-layout", json={"items": [
        {"item_id": "page-a", "x": 0, "y": 0}, {"item_id": "doc:page-b", "x": 400, "y": 0},
    ]})
    picture = _picture(client, "folder-M")
    width = picture.size[0]
    assert _is_red(picture.getpixel((int(width * 0.85), picture.size[1] // 2 - 10)))
    assert not _is_red(picture.getpixel((int(width * 0.15), picture.size[1] // 2 - 10)))


def test_a_group_is_outlined_and_unplaced_pages_are_drawn_below(client, db, monkeypatch, tmp_path):
    """WHY: a group (a document) must be told apart from a page, and a page nobody placed must not
    vanish from the picture."""
    _doc(db, "folder-G", None, doc_type=DocType.folder)
    _doc(db, "page-1", "folder-G")
    _doc(db, "page-2", "folder-G")
    _doc(db, "loose", "folder-G")
    _red_thumbnails(monkeypatch, tmp_path, {"page-1", "loose"})
    group = client.post("/api/documents/groups", json={"name": "Case 1", "child_ids": ["page-1", "page-2"]})
    assert group.status_code == 200, group.text
    group_id = group.json()["id"]
    client.put(f"{BASE}/folder-G/canvas-layout", json={"items": [{"item_id": group_id, "x": 0, "y": 0}]})

    picture = _picture(client, "folder-G")
    pixels = picture.load()
    blue = sum(
        1 for x in range(picture.size[0]) for y in range(picture.size[1])
        if pixels[x, y][2] > 150 and pixels[x, y][0] < 90
    )
    assert blue > 100, "the group's outline"
    top, bottom = picture.crop((0, 0, picture.size[0], picture.size[1] // 2)), picture.crop(
        (0, picture.size[1] // 2, picture.size[0], picture.size[1]))
    assert any(_is_red(p) for p in top.get_flattened_data()), "the group shows its first member's thumbnail"
    assert any(_is_red(p) for p in bottom.get_flattened_data()), "the unplaced page is in the strip below"


def test_the_picture_is_bounded_and_an_empty_folder_still_answers(client, db):
    """WHY: a 200-page board must not become a 50 MB image, and an empty board is an answer."""
    _doc(db, "folder-B", None, doc_type=DocType.folder)
    for index in range(30):
        _doc(db, f"p{index:02d}", "folder-B")
    client.put(f"{BASE}/folder-B/canvas-layout", json={"items": [
        {"item_id": f"p{index:02d}", "x": index * 900.0, "y": 0} for index in range(30)
    ]})
    assert max(_picture(client, "folder-B", max_size=512).size) <= 512
    assert client.get(f"{BASE}/folder-B/canvas-picture", params={"max_size": 99_999}).status_code == 422

    _doc(db, "folder-E", None, doc_type=DocType.folder)
    assert _picture(client, "folder-E").size[0] > 0
