"""The 2026-10-30 Air OOM at scale: a 70k-document library the shape of GHG, four DuckDB instances, an 8 GB Mac.

What the Air ran (98990d947): app.duckdb, global.fichero, GHG and GHG 12 open, each at the 256 MiB floor; a B13 recipe
writing page text and line boxes; the sidebar asking document views; the Trash polled; recipe starts asking their plan.
Document views took 5-20 s, then failed with `OutOfMemoryException ... /256.0 MiB used` (66 of 78 in a session), and
three recipe starts failed the same way (`train_offers._roots`, `catalogue_step._below`).

This test builds that library in tmp (no real data: 2 boxes, 1,117 folders of 63 pages, 30% read with ~3 KB of text
and 50 line boxes each, ~730 MiB on disk like GHG's 671 MB), opens the four instances for real through
`duckdb_session` with this Mac's memory faked to 8 GB, so each gets the share the engine computes, and then:
- the library opens without a migration failing (on the old shares its open-time canvas migration ran out of memory);
- the Air's reads and writes run at once for 30 s, each as its route runs it, on the library's own connections (the
  view, the Trash, a recipe start's roots and Catalogue plan, a recipe's page lists and page saves, the embed worker's
  own connection): no error, and the median document view takes no longer than `VIEW_SECONDS` (on the old shares
  about a minute, the thrash the Air showed before each OOM).

Marked `slow`: ~1-2 minutes. `FICHERO_AIR_SCALE_DOCS` scales the library (default 70,400).
"""
from __future__ import annotations

import asyncio
import os
import random
import threading
import time
from pathlib import Path

import pytest

from fichero_server.core import duckdb_session as ds

pytestmark = pytest.mark.slow

GIB = 1024**3
AIR_MEMORY = 8 * GIB
DOCS = int(os.environ.get("FICHERO_AIR_SCALE_DOCS", "70400"))
PAGES_PER_FOLDER = 63  # the log's `[PARALLEL] [n/63]`
LINES_PER_PAGE = 50  # "56 lines found, 50 read"
READ_PER_MILLE = 300
SECONDS = 30
#: The median document view under the load may take this long. The Air's took 5-20 s before they failed; on the old
#: shares here, about a minute; on the fix, 2-8 s on a loaded Pro (its slowest can pass 20 s, so the median is held).
VIEW_SECONDS = 15


def _build(path: Path) -> None:
    """The library, written in SQL (a minute, not ten): rows the model reads back, ids `box<b>`, `f<n>`, `p<n>_<p>`."""
    from fichero_server.db import Database
    from fichero_server.models import DocType, Document, FileType

    db = Database(path)
    db.save(Document(id="tmpl", name="t", doc_type=DocType.file, file_type=FileType.image, metadata={}))
    c, folders = db.conn, DOCS // PAGES_PER_FOLDER
    c.execute("""INSERT INTO documents SELECT documents.* REPLACE ('box'||b AS id, NULL AS parent_id, 'folder' AS doc_type,
                 NULL AS file_type, 'B'||b AS name) FROM documents, range(2) t(b) WHERE id = 'tmpl'""")
    c.execute(f"""INSERT INTO documents SELECT documents.* REPLACE ('f'||f AS id, 'box'||(f % 2) AS parent_id,
                  'folder' AS doc_type, NULL AS file_type, 'Doc'||f AS name)
                  FROM documents, range({folders}) t(f) WHERE id = 'tmpl'""")
    read = f"hash(f, p) % 1000 < {READ_PER_MILLE}"
    word = "md5(f||'-'||p||'-'||k)[1:7]||' '||md5(k||'.'||p||f)[1:5]||' '||md5(p||'+'||k||f)[1:8]||' '||md5(k||f||p)[1:4]"
    line = ("{'id': md5(f||'/'||p||'/'||k), 'bbox': [hash(k,p)%3000, hash(p,k)%3000, hash(f,k)%3000, hash(k,f)%3000],"
            " 'baseline': list_transform(range(4), j -> [hash(k,j,p)%3000, hash(j,k,f)%3000]),"
            " 'polygon': list_transform(range(12), j -> [hash(p,j,k)%3000, hash(f,j,k)%3000]),"
            " 'text': md5(k||'t'||p||f)[1:9]||' '||md5(f||'t'||k||p)[1:6], 'confidence': (hash(k,p,f)%1000)/1000.0}")
    for start in range(0, folders, 100):
        c.execute(f"""INSERT INTO documents SELECT documents.* REPLACE ('p'||f||'_'||p AS id, 'f'||f AS parent_id,
            'IMG_'||p||'.jpg' AS name, '/x/Doc'||f||'/IMG_'||p||'.jpg' AS path, p AS sequence,
            CASE WHEN {read} THEN array_to_string(list_transform(range(112), k -> {word}), ' ') END AS page_content,
            CASE WHEN {read} THEN to_json({{'reader': 'a-vision-model', 'thumbnail': 'storage/x.jpg',
                     'lines': list_transform(range({LINES_PER_PAGE}), k -> {line})}})
                 ELSE to_json({{'thumbnail': 'storage/x.jpg', 'width': 3000, 'height': 4000}}) END AS metadata)
            FROM documents, range({start}, {min(folders, start + 100)}) t(f), range({PAGES_PER_FOLDER}) u(p)
            WHERE id = 'tmpl'""")
    c.execute("DELETE FROM documents WHERE id = 'tmpl'")
    c.execute("CHECKPOINT")
    db.close()


@pytest.fixture(scope="module")
def built_library(tmp_path_factory) -> Path:
    path = tmp_path_factory.mktemp("air-build") / "fichero.duckdb"
    _build(path)
    return path


@pytest.fixture
def the_air(built_library, tmp_path, monkeypatch):
    """The Air's four instances, opened as the engine opens them, at the shares it computes for 8 GB."""
    import shutil

    from fichero_server.db import Database

    monkeypatch.delenv(ds.DUCKDB_MEMORY_LIMIT_ENV, raising=False)
    monkeypatch.setattr(ds, "physical_memory_bytes", lambda: AIR_MEMORY)
    saved = dict(ds._instances), dict(ds._applied)
    ds._instances.clear()
    ds._applied.clear()
    for name in ("GHG.fichero", "GHG 12.fichero", "global.fichero"):
        (tmp_path / name).mkdir()
    shutil.copy(built_library, tmp_path / "GHG.fichero" / "fichero.duckdb")
    app = ds.connect_utc(str(tmp_path / "app.duckdb"))
    others = [Database(tmp_path / "global.fichero" / "fichero.duckdb"), Database(tmp_path / "GHG 12.fichero" / "fichero.duckdb")]
    library = Database(tmp_path / "GHG.fichero" / "fichero.duckdb")
    worker = Database(library.path)  # the embed worker's own connection (`embeddings._embed_worker_db`)
    yield library, worker
    for db in (worker, library, *others):
        db.close()
    app.close()
    ds._instances.clear()
    ds._instances.update(saved[0])
    ds._applied.clear()
    ds._applied.update(saved[1])


def test_the_library_opens_as_the_fourth_instance_without_a_migration_failing(the_air):
    library, _ = the_air
    assert library.migration_failures == [], [f"{m.migration}: {m.message.splitlines()[0]}" for m in library.migration_failures]


def test_the_air_s_reads_and_writes_fit_its_share(the_air):
    from fichero_server.api.routes.document.documents import list_deleted_documents
    from fichero_server.api.routes.document.view import get_document_view
    from fichero_server.db.node_levels import NodeLevel
    from fichero_server.models import Document
    from fichero_server.recipes.catalogue_step import folders_to_describe
    from fichero_server.recipes.train_offers import _roots

    db, worker = the_air
    folders = [f"f{n}" for n in range(DOCS // PAGES_PER_FOLDER)]
    read_pages = [r[0] for r in db.conn.execute("SELECT id FROM documents WHERE page_content IS NOT NULL").fetchall()]
    errors: list[str] = []
    done: dict[str, int] = {}
    view_seconds: list[float] = []
    stop = time.monotonic() + SECONDS

    def view(rng, doc_id, level):
        started = time.monotonic()
        asyncio.run(get_document_view(doc_id, level=level, children=True, attachments=level is NodeLevel.stored,
                                      sort_by=None, sort_direction="asc", db=db))
        view_seconds.append(time.monotonic() - started)

    def a_page_saved(rng):  # the recipe writes a page's text and line boxes
        page = db.get(Document, rng.choice(read_pages))
        page.page_content = "lorem ipsum " * 250
        page.metadata["lines"] = [{"id": str(i), "bbox": [1, 2, 3, 4], "polygon": [[1, 2]] * 12, "text": "abc def"}
                                  for i in range(LINES_PER_PAGE)]
        db.save(page)

    def an_embed(rng):  # the embed worker reads the page and records the embed on its own connection
        page = worker.get(Document, rng.choice(read_pages))
        page.metadata["embedded_with"] = "a-model"
        worker.save(page)

    work = {
        "box view 1": lambda rng: view(rng, rng.choice(["box0", "box1"]), NodeLevel.stored),
        "box view 2": lambda rng: view(rng, rng.choice(["box0", "box1"]), NodeLevel.stored),
        "box view 3": lambda rng: view(rng, rng.choice(["box0", "box1"]), NodeLevel.stored),
        "folder view": lambda rng: view(rng, rng.choice(folders), NodeLevel.content),
        "trash": lambda rng: asyncio.run(list_deleted_documents(db=db, limit=None, offset=0, readable=lambda rows: (rows, 0))),
        "start: roots": lambda rng: _roots(db),
        "start: catalogue plan": lambda rng: folders_to_describe(
            db, [d.id for d in db.query_fields(Document, ["id"], parent_id=rng.choice(folders))]),
        "recipe page list 1": lambda rng: db.query(Document, parent_id=rng.choice(folders)),
        "recipe page list 2": lambda rng: db.query(Document, parent_id=rng.choice(folders)),
        "recipe save": a_page_saved,
        "embed": an_embed,
    }

    def guarded(name, fn):
        def run():
            rng = random.Random(name)
            while time.monotonic() < stop and not errors:
                try:
                    fn(rng)
                    done[name] = done.get(name, 0) + 1
                except Exception as exc:  # noqa: BLE001 -- the assertion
                    errors.append(f"{name}: {type(exc).__name__}: {str(exc).splitlines()[0]}")
        return run

    threads = [threading.Thread(target=guarded(name, fn), daemon=True) for name, fn in work.items()]
    for t in threads:
        t.start()
    for t in threads:
        t.join(SECONDS + 300)
    assert not any(t.is_alive() for t in threads), f"still running after {SECONDS + 300} s: {done}"
    assert not errors, errors
    assert set(done) == set(work), f"never finished: {set(work) - set(done)}"
    view_seconds.sort()
    typical = view_seconds[len(view_seconds) // 2]
    print(f"views: {len(view_seconds)}, median {typical:.1f} s, slowest {view_seconds[-1]:.1f} s; {done}")
    assert typical <= VIEW_SECONDS, f"a typical document view took {typical:.0f} s (the Air's thrash): {done}"


def test_the_air_s_share_is_what_a_library_of_this_size_needs(monkeypatch):
    """The arithmetic alone, so a change to the budget fails here in a second: a library on an 8 GB Mac with two
    libraries open gets at least 448 MiB, and few threads."""
    monkeypatch.delenv(ds.DUCKDB_MEMORY_LIMIT_ENV, raising=False)
    monkeypatch.setattr(ds, "physical_memory_bytes", lambda: AIR_MEMORY)
    assert ds.instance_limit_bytes(4, 2) >= 448 * 1024**2
    assert ds.threads_per_instance() == ds.THREADS_ON_A_SMALL_MAC
