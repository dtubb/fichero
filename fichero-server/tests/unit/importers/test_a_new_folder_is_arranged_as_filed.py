"""A newly imported folder is laid out on its canvas as filed (#5585, `library.canvas.arranged-at-import`).

Spec: docs/contributor_manual/specs/ui/library-view-modes.md, section I. After linking a 203-page
box, its canvas showed every page "not placed": nothing had ever saved a place for them. The
import now runs the one arrange action (`canvas.arrange`) for each folder it filled that has no
saved layout, and never touches a layout someone made. Through the real `import.folder` action
and the real canvas-layout route.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import fichero_server.api.routes.ingest  # noqa: F401  (registers import.folder)
import fichero_server.api.routes.interpretation.canvas  # noqa: F401  (registers canvas.arrange)
from fichero_server.actions.registry import ActionContext, registry
from fichero_server.models import DocType, Document
from fichero_server.models.canvas import CanvasLayout

BASE = "/api/canvas/folders"


def _image(path: Path) -> None:
    from PIL import Image

    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (40, 60), "white").save(path)


@pytest.fixture
def box(tmp_path) -> Path:
    folder = tmp_path / "Box 12"
    for name in ("f003.png", "f001.png", "f010.png", "f002.png"):
        _image(folder / name)
    _image(folder / "Legajo 2" / "g001.png")
    _image(folder / "Legajo 2" / "g002.png")
    return folder


def _import(db, folder: Path) -> list[str]:
    ctx = ActionContext(actor="historian", library_path=str(Path(db.path).parent), is_bootstrap=True)
    return registry.invoke(db, "import.folder", {"path": str(folder)}, ctx).result["document_ids"]


def _folder(db, name: str) -> Document:
    [folder] = [d for d in db.query(Document, name=name) if d.doc_type == DocType.folder]
    return folder


def _placed(client, folder_id: str) -> list[str]:
    """The card ids the app reads back, in the order the arrangement filed them."""
    rows = client.get(f"{BASE}/{folder_id}/canvas-layout").json()["items"]
    return [row["item_id"] for row in sorted(rows, key=lambda r: r["z_index"])]


def test_a_folder_ingest_places_every_page_in_filed_order(client, db, box):
    """WHY: the box opened with all its pages in the "not placed" strip. Every child, the subfolder
    card included, now has a saved place under the app's own card id, in folder order; and the
    subfolder, also new, is laid out too."""
    _import(db, box)
    top = _folder(db, "Box 12")
    children = sorted(db.query(Document, parent_id=top.id), key=lambda d: (d.sort_order or 0, d.name or ""))
    assert [d.name for d in children] == ["Legajo 2", "f001.png", "f002.png", "f003.png", "f010.png"]
    assert _placed(client, top.id) == [f"doc:{d.id}" for d in children]

    sub = _folder(db, "Legajo 2")
    names = {d.id: d.name for d in db.query(Document, parent_id=sub.id)}
    assert [names[i.removeprefix("doc:")] for i in _placed(client, sub.id)] == ["g001.png", "g002.png"]

    # Every page has its own place: nothing stacked on another.
    rows = client.get(f"{BASE}/{top.id}/canvas-layout").json()["items"]
    assert len({(r["x"], r["y"]) for r in rows}) == len(children)


def test_the_canvas_picture_has_no_page_not_placed(client, db, box):
    """WHY: the agent's picture of the board is how #5585 was seen. Its "not placed" strip lists
    children with no saved row; after an import it lists none."""
    from fichero_server.canvas_picture import _strip_node_prefix

    _import(db, box)
    top = _folder(db, "Box 12")
    placed = {_strip_node_prefix(i) for i in _placed(client, top.id)}
    assert [d.name for d in db.query(Document, parent_id=top.id) if d.id not in placed] == []
    response = client.get(f"{BASE}/{top.id}/canvas-picture")
    assert response.status_code == 200, response.text


def test_a_folder_someone_laid_out_is_untouched_by_a_later_import(client, db, box):
    """WHY: an import must never overwrite a layout a person made. The folder is laid out by hand,
    a new page arrives in it, and the hand-made places stay exactly where they were."""
    _import(db, box)
    top = _folder(db, "Box 12")
    first = sorted(db.query(Document, parent_id=top.id), key=lambda d: d.name or "")[0]
    moved = client.put(f"{BASE}/{top.id}/canvas-layout",
                       json={"items": [{"item_id": f"doc:{first.id}", "x": 999.0, "y": -40.0}]})
    assert moved.status_code == 200, moved.text
    before = {r.item_id: (r.x, r.y, r.z_index) for r in db.query(CanvasLayout, folder_id=top.id)}

    _image(box / "f000.png")
    _import(db, box)

    after = {r.item_id: (r.x, r.y, r.z_index) for r in db.query(CanvasLayout, folder_id=top.id)}
    assert after == before
    assert after[f"doc:{first.id}"][:2] == (999.0, -40.0)


def test_a_failed_arrangement_is_reported_and_the_files_are_still_in(db, box, monkeypatch):
    """WHY: an arrangement is not the import; if it fails, the pages are in and the action's
    result says which folder was not arranged and why, rather than a log line nobody reads."""
    import fichero_server.api.routes.interpretation.canvas as canvas

    def refuse(*args, **kwargs):
        raise RuntimeError("the board is locked")

    monkeypatch.setattr(canvas, "arrange_impl", refuse)
    ctx = ActionContext(actor="historian", library_path=str(Path(db.path).parent), is_bootstrap=True)
    result = registry.invoke(db, "import.folder", {"path": str(box)}, ctx).result
    assert len(result["document_ids"]) == 6
    top = _folder(db, "Box 12")
    assert result["interchange"]["not_arranged"][top.id] == "the board is locked"

