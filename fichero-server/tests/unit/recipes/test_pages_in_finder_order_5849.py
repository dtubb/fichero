"""#5849: a run's pages are queued and taken in Finder order (natural name sort): IMG_2 before IMG_10."""
from __future__ import annotations

import asyncio

from fichero_server.models import DocType, Document, FileType

NAMES = ["IMG_10.png", "IMG_2.png", "IMG_017.png", "IMG_1.png", "IMG_002b.png", "IMG_9.png"]


def test_the_material_comes_in_natural_name_order(db):
    ids = {}
    for name in NAMES:  # saved in a shuffled order, so creation order is not the answer
        doc = Document(name=name, doc_type=DocType.file, file_type=FileType.image, path=f"/x/{name}")
        db.save(doc)
        ids[doc.id] = name
    assert [ids[i] for i in db.unit_of_work_ids()] == [
        "IMG_1.png", "IMG_2.png", "IMG_002b.png", "IMG_9.png", "IMG_10.png", "IMG_017.png"]


def test_the_kraken_gate_lets_pages_in_the_order_they_came():
    from fichero_server.workflows.tools import vision_base

    order = []

    async def page(n):
        async with vision_base._KRAKEN_PAGE_GATE:
            order.append(n)
            await asyncio.sleep(0.01)

    async def go():
        await asyncio.gather(*(page(n) for n in range(12)))

    asyncio.run(go())
    assert order == list(range(12))
    assert vision_base._KrakenPageGate.in_flight == 0
    assert not vision_base._KrakenPageGate._queue


def test_two_boxes_that_each_hold_a_folder_1_stay_apart(db):
    """WHY (review 267 LOW): sorting by the immediate parent's name interleaved same-named folders of different boxes."""
    def save(name, doc_type, parent=None, sort_order=0, **kw):
        doc = Document(name=name, doc_type=doc_type, parent_id=parent, sort_order=sort_order, **kw)
        db.save(doc)
        return doc.id

    box_b = save("Box 2", DocType.folder, sort_order=2)
    box_a = save("Box 10", DocType.folder, sort_order=1)  # the person put Box 10 first
    names = {}
    for box, label in ((box_b, "B"), (box_a, "A")):
        for folder in ("Folder 2", "Folder 1"):
            f = save(folder, DocType.folder, parent=box)
            for n in ("IMG_10.png", "IMG_2.png"):
                names[save(n, DocType.file, parent=f, file_type=FileType.image, path=f"/x/{label}/{folder}/{n}")] = \
                    f"{label}/{folder}/{n}"
    assert [names[i] for i in db.unit_of_work_ids()] == [
        f"{label}/{folder}/{n}" for label in ("A", "B") for folder in ("Folder 1", "Folder 2")
        for n in ("IMG_2.png", "IMG_10.png")]
