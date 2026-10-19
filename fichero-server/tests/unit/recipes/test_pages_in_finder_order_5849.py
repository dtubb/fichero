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
