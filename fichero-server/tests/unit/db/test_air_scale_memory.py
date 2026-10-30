"""The 2026-10-30 Air OOM at scale: a 70k-document library the shape of GHG, under an 8 GB Mac's DuckDB share.

What the Air ran: the engine with four DuckDB instances open (app.duckdb, global.fichero, GHG, GHG 12) on 8 GB, a
B13 recipe run writing page text and line boxes, the sidebar asking document views, the Trash polled, a recipe start
asking the project's roots. Each of those reads failed with `OutOfMemoryException ... /256.0 MiB used`, 170 times.

This test builds that library in tmp (no real data: 2 boxes, 1,100 folders, 63 pages each, ~30% read with ~3 KB of
text and 50 line boxes each -- the shape, from the log's counts) and runs the same reads at once, each as the route
runs it, under the limit `duckdb_session` computes for an 8 GB Mac with those four instances open. It fails on the
code as it was (`BUDGET_FRACTION` alone, an equal split, `SELECT *` everywhere) and must stay green: it is the one
check that the engine fits a 100k-page library on 8 GB (the north star).

Marked `slow`: ~2 minutes to build. `FICHERO_AIR_SCALE_DOCS` scales the library (default 70,400).
"""
from __future__ import annotations

import os
import random
import string
import threading
import time
from pathlib import Path

import pytest

from fichero_server.core import duckdb_session as ds
from fichero_server.models import Document

pytestmark = pytest.mark.slow

GIB = 1024**3
AIR_MEMORY = 8 * GIB
#: The Air's four open instances: the engine's two, and two libraries.
AIR_SMALL_INSTANCES, AIR_LIBRARIES = 2, 2
DOCS = int(os.environ.get("FICHERO_AIR_SCALE_DOCS", "70400"))
PAGES_PER_FOLDER = 63  # the log's `[PARALLEL] [n/63]`
LINES_PER_PAGE = 50  # "56 lines found, 50 read"
READ_FRACTION = 0.3


def air_library_limit_bytes() -> int:
    """What one library instance gets on the Air, by the module's own arithmetic (the fix is in these functions)."""
    return ds.instance_limit_bytes(AIR_SMALL_INSTANCES + AIR_LIBRARIES, AIR_SMALL_INSTANCES)


def _build(package: Path):
    from fichero_server.db import Database
    from fichero_server.models import DocType, FileType

    rng = random.Random(1)

    def words(n: int) -> str:
        return " ".join("".join(rng.choices(string.ascii_lowercase, k=rng.randint(3, 9))) for _ in range(n))

    def line_boxes() -> dict:
        return {"lines": [{"id": "".join(rng.choices(string.hexdigits, k=32)), "bbox": [rng.randint(0, 3000) for _ in range(4)],
                           "text": words(8), "confidence": round(rng.random(), 3)} for _ in range(LINES_PER_PAGE)],
                "reader": "a-vision-model"}

    package.mkdir(parents=True)
    db = Database(package / "fichero.duckdb")
    folders: list[Document] = []
    per_box = max(1, DOCS // PAGES_PER_FOLDER // 2)
    for b in range(2):
        box = Document(name=f"B{b}", doc_type=DocType.folder)
        db.save(box)
        folders += [Document(name=f"Doc{f}", doc_type=DocType.folder, parent_id=box.id) for f in range(per_box)]
    for start in range(0, len(folders), 500):
        db.save_many(folders[start:start + 500], new=True)
    for folder in folders:
        read = rng.random() < READ_FRACTION
        db.save_many([Document(name=f"IMG_{p:03d}.jpg", doc_type=DocType.file, file_type=FileType.image, parent_id=folder.id,
                               path=f"/x/{folder.name}/IMG_{p:03d}.jpg", sequence=p,
                               page_content=words(450) if read else None,
                               metadata=line_boxes() if read else {"thumbnail": "storage/x.jpg"})
                      for p in range(PAGES_PER_FOLDER)], new=True)
    db.conn.execute("CHECKPOINT")
    return db


@pytest.fixture(scope="module")
def air_library(tmp_path_factory):
    """One library for the module (a build is ~2 minutes), opened at the Air's computed share and threads."""
    package = tmp_path_factory.mktemp("air") / "GHG.fichero"
    db = _build(package)
    yield db
    db.close()


def _at_the_airs_share(db, monkeypatch) -> None:
    monkeypatch.setattr(ds, "physical_memory_bytes", lambda: AIR_MEMORY)
    limit = air_library_limit_bytes()
    db.conn.execute(f"SET memory_limit='{limit // 1024**2}MiB'")
    threads = ds.threads_per_instance()
    db.conn.execute(f"SET threads={threads}" if threads else "RESET threads")


def test_the_air_s_reads_fit_its_share(air_library, monkeypatch):
    """The three reads that failed, as their routes run them, at once with the recipe writing, for 30 s, no error."""
    from fichero_server.api.routes.document.documents import _batched_children_of, _list_documents
    from fichero_server.api.routes.document.trash import trashed_items
    from fichero_server.db.node_levels import NodeLevel, resolve_level
    from fichero_server.recipes.train_offers import _roots

    db = air_library
    _at_the_airs_share(db, monkeypatch)
    boxes = [d.id for d in db.query_fields(Document, ["id"], parent_id=None)]
    folders = [r[0] for r in db.conn.execute("SELECT id FROM documents WHERE doc_type = 'folder' AND parent_id IS NOT NULL").fetchall()]
    rng = random.Random(3)
    errors: list[str] = []
    stop = time.monotonic() + 30
    done = {"views": 0, "trash": 0, "roots": 0, "writes": 0}

    def guarded(name, fn):
        def run():
            while time.monotonic() < stop and not errors:
                try:
                    fn()
                    done[name] += 1
                except Exception as exc:  # noqa: BLE001 -- the assertion
                    errors.append(f"{name}: {type(exc).__name__}: {str(exc).splitlines()[0]}")
                    return
        return run

    def a_document_view():  # view.py `_fetch` at the stored tier: a box's folders
        rows = _list_documents(db, parent_id=rng.choice(boxes))
        resolve_level(db, rows, NodeLevel.stored, children_of=_batched_children_of(db, rows, NodeLevel.stored))

    def a_recipe_page():  # the recipe saves a page read: text and line boxes, ON CONFLICT
        kids = db.query(Document, parent_id=rng.choice(folders))
        page = rng.choice(kids)
        page.page_content = "lorem " * 500
        page.metadata["lines"] = [{"id": str(i), "bbox": [1, 2, 3, 4], "text": "abc def ghi"} for i in range(LINES_PER_PAGE)]
        db.save(page)

    workers = [threading.Thread(target=guarded(name, fn), daemon=True) for name, fn in (
        ("views", a_document_view), ("views", a_document_view), ("trash", lambda: trashed_items(db)),
        ("roots", lambda: _roots(db)), ("writes", a_recipe_page))]
    for w in workers:
        w.start()
    for w in workers:
        w.join(120)
    assert not errors, errors
    assert all(done.values()), done


def test_the_air_s_share_is_what_a_library_of_this_size_needs(monkeypatch):
    """The arithmetic alone, so a change to the budget fails here in a second, not after a two-minute build: a library
    on an 8 GB Mac with two libraries open gets at least 448 MiB (measured peak for the reads above: ~260 MiB with the
    slim reads, ~700 MiB with the old `SELECT *` ones), and few threads."""
    monkeypatch.setattr(ds, "physical_memory_bytes", lambda: AIR_MEMORY)
    assert air_library_limit_bytes() >= 448 * 1024**2
    assert ds.threads_per_instance() == ds.THREADS_ON_A_SMALL_MAC
