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
import subprocess
import sys
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
#: One Start-plan or after-step read on the whole library may raise the engine's peak by this much, DuckDB's own 448 MiB
#: share included. Before the slim reads `counted` raised it by 2.2 GiB, a whole box's Catalogue plan by 1.5-2.1 GiB,
#: `material` by 2.9 GiB.
READER_PEAK_MIB = 800
ALL_KNOWS_DONE = ("split-pages", "find-regions", "find-lines", "read-a-line", "read-a-page", "prepare-the-image", "correct",
                  "find-names-tag-words", "split-into-entries", "leave-out", "translate-transliterate-normalise")
#: A 63-page folder's pages, in a library of 20k cut pages (the old read: +849 MiB here, +1.2 GiB at 70k). `unit_of_work_ids`
#: still costs the library: this bounds the metadata, which is the rest.
CUT_FOLDER_PEAK_MIB = 250


def _build(path: Path, docs: int = DOCS, cut: bool = False) -> None:
    """The library, written in SQL (a minute, not ten): rows the model reads back, ids `box<b>`, `f<n>`, `p<n>_<p>`."""
    from fichero_server.db import Database
    from fichero_server.models import Artifact, ContentRepresentation, DocType, Document, FileType
    from fichero_server.models.anchors import SourceAnchor
    from fichero_server.models.segments import ProvenanceKind, Segment, SegmentPass

    db = Database(path)
    db.save(Document(id="tmpl", name="t", doc_type=DocType.file, file_type=FileType.image, metadata={}))
    db.save(Artifact(id="tmpl", document_id="tmpl", artifact_type="transcription", model="a-vision-model", data={}))
    db.save(SegmentPass(id="tmpl", document_id="tmpl", name="reading", provenance_kind=ProvenanceKind.workflow, model="a-vision-model"))
    anchor = SourceAnchor(document_id="tmpl", rect=[0.1, 0.1, 0.6, 0.05])
    db.save(Segment(id="tmpl", document_id="tmpl", pass_id="tmpl", kind="line", anchor=anchor, bbox_x=0.1, bbox_y=0.1, bbox_w=0.6,
                    bbox_h=0.05, tile="t", doc_kind="tmpl:line", provenance_kind=ProvenanceKind.workflow))
    db.save(ContentRepresentation(id="tmpl", document_id="tmpl", segment_id="tmpl", kind="transcription", content="texto", source_anchor=anchor))
    c, folders = db.conn, docs // PAGES_PER_FOLDER
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
    if cut:  # pages cut from photographs: a `chunk` whose metadata names its photograph, beside its line boxes
        c.execute("""UPDATE documents SET doc_type = 'chunk', file_type = NULL,
                     metadata = json_merge_patch(metadata, '{"split_source_id": "a-photograph"}') WHERE id LIKE 'p%'""")
    # Each read page: its reader's transcription artifact (the text and the line boxes again) and its pass.
    c.execute("""INSERT INTO artifacts SELECT artifacts.* REPLACE ('a'||d.id AS id, d.id AS document_id,
                  d.page_content AS content, d.metadata AS data)
                  FROM artifacts, documents d WHERE artifacts.id = 'tmpl' AND d.page_content IS NOT NULL""")
    c.execute("""INSERT INTO segment_passes SELECT segment_passes.* REPLACE ('pass'||d.id AS id, d.id AS document_id)
                  FROM segment_passes, documents d WHERE segment_passes.id = 'tmpl' AND d.page_content IS NOT NULL""")
    # And its lines, each with its reading: a million rows of each.
    c.execute(f"""INSERT INTO segments SELECT segments.* REPLACE ('s'||d.id||'_'||k AS id, d.id AS document_id, 'pass'||d.id AS pass_id)
                  FROM segments, documents d, range({LINES_PER_PAGE}) t(k) WHERE segments.id = 'tmpl' AND d.page_content IS NOT NULL""")
    c.execute(f"""INSERT INTO contentrepresentations SELECT contentrepresentations.* REPLACE ('r'||d.id||'_'||k AS id, d.id AS document_id,
                  's'||d.id||'_'||k AS segment_id, md5(d.id||k)||' '||md5(k||d.id) AS content)
                  FROM contentrepresentations, documents d, range({LINES_PER_PAGE}) t(k)
                  WHERE contentrepresentations.id = 'tmpl' AND d.page_content IS NOT NULL""")
    for table in ("contentrepresentations", "segments", "artifacts", "segment_passes"):
        c.execute(f"DELETE FROM {table} WHERE id = 'tmpl'")
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
        "start: whole box catalogue plan": lambda rng: folders_to_describe(
            db, [p.id for f in db.query_fields(Document, ["id"], parent_id=rng.choice(["box0", "box1"]))
                 for p in db.query_fields(Document, ["id"], parent_id=f.id)]),
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


_PROBE = """
import os, resource, sys, threading, time
def _guard():  # HARD: a probe never takes the machine with it
    while True:
        time.sleep(1)
        if resource.getrusage(resource.RUSAGE_SELF).ru_maxrss > 3 * 1024**3:
            print("OVER 3 GiB", flush=True)
            os._exit(3)
threading.Thread(target=_guard, daemon=True).start()
from fichero_server.core import duckdb_session as ds
ds.physical_memory_bytes = lambda: 8 * 1024**3
from fichero_server.db import Database
from fichero_server.models import Document
from fichero_server.recipes import catalogue_step, done, train_offers
db = Database(sys.argv[1])
box_pages = [p.id for f in db.query_fields(Document, ["id"], parent_id="box0") for p in db.query_fields(Document, ["id"], parent_id=f.id)]
before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
exec(sys.argv[2])
print("PEAK", (resource.getrusage(resource.RUSAGE_SELF).ru_maxrss - before) // 1024**2, flush=True)
"""


@pytest.fixture(scope="module")
def probed(built_library, tmp_path_factory):
    """Run one reader in a process of its own, as the engine holds it at the Air's share: how many MiB it raised the
    process's peak by (macOS `ru_maxrss`, bytes). Own process: a freed heap in this one would hide the peak."""
    home = tmp_path_factory.mktemp("air-probe-home")
    env = {**os.environ, "HOME": str(home), "FICHERO_BASE_PATH": str(home), "FICHERO_DUCKDB_MEMORY_LIMIT": "448MiB",
           "PYTHONPATH": str(Path(__file__).parents[3] / "src")}

    def run(code: str, library: Path = built_library) -> int:
        finished = subprocess.run([sys.executable, "-c", _PROBE, str(library), code], env=env, capture_output=True, text=True, timeout=900)
        assert finished.returncode == 0, finished.stderr[-800:]
        peak = int(finished.stdout.split("PEAK")[-1])
        print(f"{code[:70]}: +{peak} MiB")
        return peak

    run("pass")  # the first open rebuilds the indexes (#5644): its spike would hide what the reader adds
    return run


@pytest.fixture(scope="module")
def cut_library(tmp_path_factory) -> Path:
    path = tmp_path_factory.mktemp("air-cut") / "fichero.duckdb"
    _build(path, docs=20_000, cut=True)
    return path


def test_a_small_folder_of_cut_pages_reads_the_folder_not_the_library(cut_library, probed):
    """Review H1 (a regression of the sweep): `split_pages` read every cut page's metadata, then filtered: 60 s and +1.2 GiB
    for 63 pages in a library of 70k cut pages. The folder's plan reads the folder (#6268)."""
    code = """
within = {d.id for d in db.query_fields(Document, ["id"], parent_id="f0")}
assert len(done.pages_for(db, {}, None, within)) == 63
assert done.material(db, within)["pages"] == 63
"""
    assert probed(code, library=cut_library) <= CUT_FOLDER_PEAK_MIB


def test_a_certainty_bar_stays_lean(probed):
    """Review H3: with `only_below_confidence` the plan read every line whole; over the library, unfinished at 32 minutes."""
    assert probed("known = done.kraken_lines_known(db, box_pages); assert known['lines'] > 400000") <= READER_PEAK_MIB


def test_every_step_a_recipe_can_turn_on_stays_lean(probed):
    """The steps a plan reaches only when the recipe has them: each `done.KNOWS_DONE` job, over a whole box."""
    cards = [{"job": job, "card": "workflow", "steps": [job], "model_override": "m", "model": "m",
              "tool_config": {"analyze": {"reading_kind": "translation"}}} for job in sorted(ALL_KNOWS_DONE)]
    code = f"for card in {cards!r}: done._split_done(db, card, box_pages)"
    assert probed(code) <= READER_PEAK_MIB


def test_a_plan_with_every_option_that_adds_a_read_stays_lean(probed):
    """Review H3, through the real `_start_plan`: every `KNOWS_DONE` step, the Catalogue, a certainty bar, cloud over its cap
    (so `first_pages_that_fit` runs), and the corrected-lines count `held_after_failure` asks."""
    code = """
from pathlib import Path
from fichero_server.api.routes.system import recipes as r
from fichero_server.llm import spend
from fichero_server.recipes import project, start
from fichero_server.workflows import model_comparison

cards = [{"workflow": job, "job": job, "steps": [job], "card": "workflow", "runs_on": "this-mac", "model_override": "m", "model": "m"}
         for job in ALL_KNOWS_DONE + ("describe-for-the-catalogue",)]
for card in cards:
    if card["job"] == "correct":
        card.update(runs_on="cloud:anthropic", provider_override="anthropic", tool_config={"transcribe_review": {"only_below_confidence": 0.6}})
    if card["job"] == "translate-transliterate-normalise":
        card["tool_config"] = {"analyze": {"reading_kind": "translation"}}
real = start.plan_start
start.plan_start = lambda *a, **k: {**real(None, stays_local=False), "runs": cards, "workflows": cards}
model_comparison.estimate_cost = lambda model, tokens_in, tokens_out, provider="": tokens_in / 1200 * 0.01
spend.has_listed_price = lambda provider, model: True
project.write_project_setup(Path(sys.argv[1]).parent, {"cloud_spend_cap_usd": 1}, None)
plan = r._start_plan(db, None, clusters=[])
assert plan["cloud_cap"]["over"] and plan["cloud_cap"].get("fewer_pages") is not None, plan["cloud_cap"]
assert plan["estimate"]["pages"] > 60000
assert train_offers._corrected_lines(db) >= 0
assert done.material(db, set(box_pages))["pages"] == len(box_pages)
"""
    assert probed(f"ALL_KNOWS_DONE = {ALL_KNOWS_DONE!r}\n{code}") <= READER_PEAK_MIB


def test_the_canvas_backfill_fits_the_floor(built_library, tmp_path, monkeypatch):
    """Review M1: at the 256 MiB floor it failed on every open ("failed to allocate 16.0 MiB (244.5/256 MiB)"); the failure
    was recorded and the open went on."""
    import shutil

    import duckdb

    from fichero_server.db import Database

    monkeypatch.setenv(ds.DUCKDB_MEMORY_LIMIT_ENV, "256MiB")
    monkeypatch.setattr(ds, "physical_memory_bytes", lambda: AIR_MEMORY)
    (tmp_path / "L.fichero").mkdir()
    path = tmp_path / "L.fichero" / "fichero.duckdb"
    shutil.copy(built_library, path)
    with duckdb.connect(str(path)) as raw:  # as an older build left it, whichever test opened the library first
        raw.execute("DELETE FROM librarysettings WHERE id = 'canvas_layout_backfilled'")
    db = Database(path)
    assert int(db.conn.execute("SELECT current_setting('threads')").fetchone()[0]) == ds.THREADS_ON_A_SMALL_MAC
    assert db.migration_failures == [], [f"{m.migration}: {m.message.splitlines()[0]}" for m in db.migration_failures]
    assert db.conn.execute("SELECT count(*) FROM librarysettings WHERE id = 'canvas_layout_backfilled'").fetchone()[0] == 1
    db.close()


def test_counting_for_training_stays_lean(probed):
    """Review H1: `_teacher` and the pass counts read every transcription whole on each plan and finished step: +2.1 GiB."""
    assert probed("assert train_offers._teacher(db) == 'a-vision-model'; train_offers.counted(db)") <= READER_PEAK_MIB


def test_a_whole_box_catalogue_plan_stays_lean(probed):
    """Review H2: `folders_covering` read every page of the run whole: a box of 35k pages raised the peak by 2.1 GiB."""
    assert probed("catalogue_step.folders_to_describe(db, box_pages)") <= READER_PEAK_MIB


def test_counting_the_material_stays_lean(probed):
    """Sibling sweep: `material`, on every plan, read the whole library twice: +2.9 GiB."""
    assert probed("assert done.material(db)['pages'] > 60000") <= READER_PEAK_MIB


def test_a_whole_library_plan_s_notes_stay_lean(probed):
    """Sibling sweep: every step's pages, what each has done, who called them blank and the Catalogue's folders: the Start
    plan over the library never finished in 10 minutes, on a whole-row read a page."""
    cards = [{"job": job, "card": "workflow", "steps": [job]} for job in ("find-lines", "read-a-line", "describe-for-the-catalogue")]
    assert probed(f"done.annotate(db, {{'runs': {cards!r}}})") <= READER_PEAK_MIB


def test_the_air_s_share_is_what_a_library_of_this_size_needs(monkeypatch):
    """The arithmetic alone, so a change to the budget fails here in a second: a library on an 8 GB Mac with two
    libraries open gets at least 448 MiB, and few threads."""
    monkeypatch.delenv(ds.DUCKDB_MEMORY_LIMIT_ENV, raising=False)
    monkeypatch.setattr(ds, "physical_memory_bytes", lambda: AIR_MEMORY)
    assert ds.instance_limit_bytes(4, 2) >= 448 * 1024**2
    assert ds.threads_per_instance() == ds.THREADS_ON_A_SMALL_MAC
