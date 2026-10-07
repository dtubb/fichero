"""A picture of a folder's 2D canvas: its cards' thumbnails at their saved positions (#5568).

An agent organising a project through the MCP lays pages out, then needs to LOOK at the board
and adjust, without screen control. This draws what the saved layout says, from what is stored:

* each placed document is a card showing its stored thumbnail (a group shows its first member's,
  with a thick outline and its member count);
* each canvas item (note, text, quote) is a yellow box with its text; a link is a line between
  the two things it joins;
* every card is labelled with its name and, below it, the first 8 characters of its id, so what the agent
  sees maps back to the ids its tools take;
* a folder child with no saved position is drawn in a strip under the board, labelled
  "not placed", in folder order.

A saved ``x``/``y`` is the card's CENTRE (as the app places it). A card with no saved ``w``/``h``
is drawn ``CARD_W`` x ``CARD_H``. Only cached thumbnails are read; nothing is generated here, so
a page whose thumbnail is not yet made is a grey card with its name. The longest side of the
picture is at most ``max_size`` pixels.
"""

from __future__ import annotations

import io
import math
import textwrap
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # PIL loads only when a picture is drawn: the engine's startup import budget
    from PIL import Image, ImageFont

from fichero_server.models import DocType, Document
from fichero_server.models.canvas import CanvasItem, CanvasItemKind, CanvasLayout
from fichero_server.models.knowledge import KnowledgeEntity

CARD_W = 120.0
CARD_H = 150.0
MARGIN = 60.0
#: Unplaced children drawn at most; the rest are counted in the strip's label.
MAX_UNPLACED = 400
MIN_SIZE = 256
MAX_SIZE = 4096

_BG = (246, 245, 241)
_CARD = (255, 255, 255)
_EDGE = (150, 150, 150)
_GROUP = (40, 100, 200)
_NOTE = (255, 240, 160)
_INK = (30, 30, 30)
_FAINT = (120, 120, 120)


def _font(px: int) -> ImageFont.ImageFont:
    from PIL import ImageFont

    return ImageFont.load_default(size=max(8, px))


def _strip_node_prefix(item_id: str) -> str:
    for prefix in ("doc:", "entity:"):
        if item_id.startswith(prefix):
            return item_id[len(prefix):]
    return item_id


def _label(name: str | None, item_id: str) -> str:
    """Two lines under a card: its name, then the first 8 characters of its id."""
    return f"{(name or '').strip() or '(untitled)'}\n{item_id[:8]}"


def _fit(text: str, font: ImageFont.ImageFont, width: float) -> str:
    """Each line of `text` cut to `width` pixels, so a label never runs under its neighbour."""
    lines = []
    for line in text.split("\n"):
        if font.getlength(line) > width:
            while line and font.getlength(line + "...") > width:
                line = line[:-1]
            line += "..."
        lines.append(line)
    return "\n".join(lines)


def _group_members(db: Any, group_id: str) -> list[Document]:
    return sorted(db.query(Document, parent_id=group_id), key=lambda d: (d.sort_order or 0, d.name or ""))


def _card_for(db: Any, item_id: str) -> dict | None:
    """What a layout row's item IS, as a card to draw; None for something the canvas cannot show."""
    bare = _strip_node_prefix(item_id)
    doc = db.get(Document, bare)
    if doc is not None:
        card: dict = {"kind": "doc", "doc": doc, "id": doc.id, "label": _label(doc.name, doc.id)}
        if doc.doc_type == DocType.group or doc.node_kind == "group":
            members = _group_members(db, doc.id)
            card.update(kind="group", members=len(members), thumb_doc=members[0] if members else None)
        return card
    canvas_item = db.get(CanvasItem, bare)
    if canvas_item is not None:
        return {"kind": "item", "item": canvas_item, "id": canvas_item.id}
    entity = db.get(KnowledgeEntity, bare)
    if entity is not None:
        return {"kind": "entity", "id": entity.id, "label": _label(getattr(entity, "name", None), entity.id)}
    return None


def _thumbnail(doc: Document | None, package_path: Path | None, db: Any) -> Image.Image | None:
    from PIL import Image

    if doc is None:
        return None
    from fichero_server.db.storage import get_thumbnail

    try:
        path = get_thumbnail(doc, package_path=package_path, db=db)
        if not path or not Path(path).exists():
            return None
        with Image.open(path) as image:
            return image.convert("RGB")
    except Exception:  # a broken cache file is a grey card, not a failed picture
        return None


def render_canvas_picture(
    db: Any,
    folder_id: str,
    rows: list[CanvasLayout],
    *,
    package_path: Path | None = None,
    max_size: int = 1600,
) -> bytes:
    """Draw the folder's board as one PNG (see the module docstring for what is drawn)."""
    from PIL import Image, ImageDraw, ImageOps

    max_size = max(MIN_SIZE, min(MAX_SIZE, int(max_size)))
    placed: list[tuple[CanvasLayout, dict]] = []
    links: list[CanvasItem] = []
    placed_ids: set[str] = set()
    for row in rows:
        card = _card_for(db, row.item_id)
        if card is None:
            continue
        if card["kind"] == "item" and card["item"].kind == CanvasItemKind.link:
            links.append(card["item"])
            continue
        placed.append((row, card))
        placed_ids.add(card["id"])
    # Links are drawn whether or not they have a layout row of their own.
    for item in db.query(CanvasItem, folder_id=folder_id):
        if item.kind == CanvasItemKind.link and item.id not in {link.id for link in links}:
            links.append(item)

    children = sorted(
        db.query(Document, parent_id=folder_id), key=lambda d: (d.sort_order or 0, d.name or "")
    )
    unplaced_all = [doc for doc in children if doc.id not in placed_ids]
    unplaced = unplaced_all[:MAX_UNPLACED]

    # World boxes: (left, top, right, bottom) per placed card, centre-anchored.
    boxes: list[tuple[float, float, float, float]] = []
    for row, _card in placed:
        w = row.w or CARD_W
        h = row.h or CARD_H
        boxes.append((row.x - w / 2, row.y - h / 2, row.x + w / 2, row.y + h / 2))
    if boxes:
        left = min(b[0] for b in boxes)
        top = min(b[1] for b in boxes)
        right = max(b[2] for b in boxes)
        bottom = max(b[3] for b in boxes)
    else:
        left = top = right = bottom = 0.0

    # The "not placed" strip under the board, in a grid as wide as the board (or a square).
    strip: list[tuple[Document, tuple[float, float, float, float]]] = []
    if unplaced:
        gap = 30.0
        columns = max(1, int((right - left) // (CARD_W + gap)) if boxes else math.ceil(math.sqrt(len(unplaced))))
        strip_top = (bottom + MARGIN * 1.5) if boxes else 0.0
        for index, doc in enumerate(unplaced):
            col, line = index % columns, index // columns
            x0 = left + col * (CARD_W + gap)
            y0 = strip_top + line * (CARD_H + gap + 30)
            strip.append((doc, (x0, y0, x0 + CARD_W, y0 + CARD_H)))
        right = max(right, max(b[1][2] for b in strip))
        bottom = max(bottom, max(b[1][3] for b in strip))
        if not boxes:
            left, top = 0.0, 0.0

    world_w = (right - left) + 2 * MARGIN
    world_h = (bottom - top) + 2 * MARGIN + 30
    scale = min(max_size / world_w, max_size / world_h, 2.0)
    width = max(1, int(world_w * scale))
    height = max(1, int(world_h * scale))
    picture = Image.new("RGB", (width, height), _BG)
    draw = ImageDraw.Draw(picture)
    font = _font(int(12 * max(scale, 0.6)))

    def to_px(box: tuple[float, float, float, float]) -> tuple[int, int, int, int]:
        return (
            int((box[0] - left + MARGIN) * scale),
            int((box[1] - top + MARGIN) * scale),
            int((box[2] - left + MARGIN) * scale),
            int((box[3] - top + MARGIN) * scale),
        )

    centres = {card["id"]: ((b[0] + b[2]) / 2, (b[1] + b[3]) / 2) for (_r, card), b in zip(placed, boxes)}
    for link in links:
        ends = [centres.get(_strip_node_prefix(i or "")) for i in (link.source_item_id, link.target_item_id)]
        if all(ends):
            (x1, y1), (x2, y2) = ends  # type: ignore[misc]
            a = to_px((x1, y1, x1, y1))
            b = to_px((x2, y2, x2, y2))
            draw.line((a[0], a[1], b[0], b[1]), fill=_FAINT, width=max(1, int(2 * scale)))

    def draw_card(rect: tuple[int, int, int, int], thumb_doc: Document | None, label: str, *, group: int | None,
                  faint: bool = False) -> None:
        draw.rectangle(rect, fill=_CARD, outline=_EDGE)
        thumb = _thumbnail(thumb_doc, package_path, db)
        inner_w, inner_h = rect[2] - rect[0] - 4, rect[3] - rect[1] - 4
        if thumb is not None and inner_w > 2 and inner_h > 2:
            thumb = ImageOps.contain(thumb, (inner_w, inner_h))
            picture.paste(thumb, (rect[0] + 2 + (inner_w - thumb.width) // 2, rect[1] + 2 + (inner_h - thumb.height) // 2))
        if group is not None:
            width_px = max(2, int(4 * scale))
            pad = width_px + 1
            draw.rectangle((rect[0] - pad, rect[1] - pad, rect[2] + pad, rect[3] + pad), outline=_GROUP, width=width_px)
            label = f"group: {label} · {group} pages"
        draw.multiline_text(
            (rect[0], rect[3] + 3 + (pad if group is not None else 0)),
            _fit(label, font, rect[2] - rect[0] + 20 * scale),
            fill=_GROUP if group is not None else (_FAINT if faint else _INK),
            font=font,
        )

    for (row, card), box in zip(placed, boxes):
        rect = to_px(box)
        if card["kind"] == "item":
            item = card["item"]
            draw.rectangle(rect, fill=_NOTE, outline=_EDGE)
            chars = max(6, int((rect[2] - rect[0]) / max(6.0, 7 * max(scale, 0.6))))
            text = "\n".join(textwrap.wrap(item.text or f"({item.kind.value})", chars)[:8])
            draw.multiline_text((rect[0] + 4, rect[1] + 4), text, fill=_INK, font=font)
            draw.text((rect[0], rect[3] + 3), f"{item.kind.value} {item.id[:8]}", fill=_FAINT, font=font)
        elif card["kind"] == "group":
            draw_card(rect, card.get("thumb_doc"), card["label"], group=card["members"])
        elif card["kind"] == "doc":
            draw_card(rect, card["doc"], card["label"], group=None)
        else:
            draw_card(rect, None, card["label"], group=None)

    if strip:
        first = to_px(strip[0][1])
        more = len(unplaced_all) - len(unplaced)
        title = f"not placed ({len(unplaced_all)})" + (f", first {len(unplaced)} drawn" if more else "")
        draw.text((first[0], max(0, first[1] - int(20 * max(scale, 0.6)))), title, fill=_FAINT, font=font)
        for doc, box in strip:
            is_group = doc.doc_type == DocType.group or doc.node_kind == "group"
            members = _group_members(db, doc.id) if is_group else []
            draw_card(
                to_px(box),
                (members[0] if members else None) if is_group else doc,
                _label(doc.name, doc.id),
                group=len(members) if is_group else None,
                faint=True,
            )

    out = io.BytesIO()
    picture.save(out, format="PNG", optimize=True)
    return out.getvalue()
