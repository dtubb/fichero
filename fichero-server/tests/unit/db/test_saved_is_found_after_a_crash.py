"""What was saved is found after the engine dies mid-work (#5644, `source.store.saved-is-found-after-a-crash`,
`activity.durable.run-deletable-after-a-crash`).

The maintainer's report, 2026-10-09: Detect Segments (Kraken) said it succeeded and the page showed no
segments; a failed run in Activity could not be deleted. Both were DuckDB 1.4+ writing stale secondary
indexes at the first checkpoint after replaying a WAL (`core/duckdb_session.py`). These tests do what the
app does -- a real engine process writes and is killed, the next engine opens the library -- and ask the
routes the app asks.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path
from urllib.parse import quote

import duckdb
import pytest
from fastapi.testclient import TestClient

from _scan_files import scan_rglob
from fichero_server.db import Database
from fichero_server.db.manager import db_manager
from fichero_server.models import DocType, Document, FileType, Status

# The child is a real engine process: it opens the library through the manager, saves a page's
# segment pass and lines and a failed run with its activity, and is killed before it closes --
# what quitting the app mid-run does to the engine.
_CHILD = r"""
import asyncio, json, os, signal, sys, uuid
from datetime import datetime, timezone
from pathlib import Path
import fichero_server.api.main  # noqa: F401  (import order)
from fichero_server.db.manager import db_manager
from fichero_server.models import DocType, Document, FileType, Status
from fichero_server.models.anchors import SourceAnchor
from fichero_server.models.knowledge import ProvenanceKind
from fichero_server.models.segments import Segment, SegmentPass, bbox_and_tile_from_anchor
from fichero_server.workflows.activity_store import ActivityStore
from fichero_server.workflows.activity_types import Activity, ActivityLevel, ActivityType

package = Path(sys.argv[1])
db = db_manager.get_database(package)
doc = Document(name="EAP1740_page.jpg", doc_type=DocType.file, file_type=FileType.image,
               path="/EAP1740_page.jpg", status=Status.completed)
db.save(doc)
pass_row = SegmentPass(document_id=doc.id, name="regions", provenance_kind=ProvenanceKind.workflow)
db.save(pass_row)
for i in range(85):
    anchor = SourceAnchor(document_id=doc.id, rect=[0.1, 0.01 * i, 0.6, 0.008])
    x, y, w, h, tile = bbox_and_tile_from_anchor(anchor)
    db.save(Segment(document_id=doc.id, pass_id=pass_row.id, kind="line", anchor=anchor,
                    bbox_x=x, bbox_y=y, bbox_w=w, bbox_h=h, tile=tile, doc_kind=f"{doc.id}:line",
                    provenance_kind=ProvenanceKind.workflow))
store = ActivityStore(str(package / "fichero.duckdb"))
thread_id = f"thread-{uuid.uuid4().hex[:12]}"
asyncio.run(store.save_workflow_run(thread_id=thread_id, workflow_id="wf", workflow_name="Detect Segments (Kraken)", status="running"))
for _ in range(40):
    asyncio.run(store.save(Activity(id=str(uuid.uuid4()), type=ActivityType.NODE_STARTED, level=ActivityLevel.INFO,
                                    timestamp=datetime.now(timezone.utc), message="Started", workflow_id="wf",
                                    thread_id=thread_id)))
asyncio.run(store.update_workflow_run(thread_id, status="failed"))
for _ in range(30):  # other runs, started and settled the way a working session does
    other = f"thread-{uuid.uuid4().hex[:12]}"
    asyncio.run(store.save_workflow_run(thread_id=other, workflow_id="wf", workflow_name="Read", status="running"))
    asyncio.run(store.update_workflow_run(other, status="completed"))
print(json.dumps({"doc": doc.id, "pass": pass_row.id, "thread": thread_id}), flush=True)
os.kill(os.getpid(), signal.SIGKILL)
"""


def _kill_mid_write(package: Path) -> dict:
    """Run the child engine against `package` and return the ids it saved before it was killed."""
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(sys.path)}
    out = subprocess.run([sys.executable, "-c", _CHILD, str(package)], env=env, capture_output=True, text=True,
                         timeout=300)
    assert out.returncode == -9, f"the child was meant to be killed; it exited {out.returncode}: {out.stderr[-2000:]}"
    assert (package / "fichero.duckdb.wal").exists(), "a killed engine leaves its WAL behind"
    return json.loads(out.stdout.strip().splitlines()[-1])


@pytest.fixture(scope="module")
def crashed(tmp_path_factory) -> tuple[Path, dict]:
    """A library an engine wrote to and was killed in, made once and copied by each test."""
    package = tmp_path_factory.mktemp("crashed") / "Library.fichero"
    package.mkdir()
    Database(package / "fichero.duckdb").close()  # an existing library: its tables and indexes on disk
    return package, _kill_mid_write(package)


@pytest.fixture
def package(crashed, tmp_path) -> tuple[Path, dict]:
    source, ids = crashed
    copy = tmp_path / "Library.fichero"
    shutil.copytree(source, copy)
    yield copy, ids
    db_manager.close_all()


def _index_misses(dbfile: Path, table: str, column: str, value: str) -> tuple[int, int]:
    """(rows found through the index, rows found by reading the table)."""
    conn = duckdb.connect(str(dbfile))
    try:
        through_index = conn.execute(f"SELECT count(*) FROM {table} WHERE {column} = ?", [value]).fetchone()[0]
        by_scan = conn.execute(f"SELECT count(*) FROM {table} WHERE {column} || '' = ?", [value]).fetchone()[0]
        return through_index, by_scan
    finally:
        conn.close()


def _damage_as_before_the_fix(dbfile: Path) -> None:
    """Replay and checkpoint with plain DuckDB, and forget the repair: a library from before #5644."""
    conn = duckdb.connect(str(dbfile))
    conn.execute("DELETE FROM librarysettings WHERE id = 'indexes_rebuilt_after_wal_replay_5644'")
    conn.close()


def _client(package: Path, app_db) -> TestClient:
    from fichero_server.api.main import app
    from fichero_server.api.routes.ai.providers import get_app_database
    from fichero_server.api.main import get_library_database, get_library_database_for_write

    db = db_manager.get_database(package)
    app.dependency_overrides[get_app_database] = lambda: app_db
    app.dependency_overrides[get_library_database] = lambda: db
    app.dependency_overrides[get_library_database_for_write] = lambda: db
    return TestClient(app, headers={"X-Fichero-Library-Path": quote(str(package), safe="/")})


def test_duckdb_still_writes_stale_indexes_after_a_replay(package):
    """The trigger, without the engine: replay the WAL, checkpoint, reopen -- the index misses the rows.

    A canary. When DuckDB fixes this upstream, this fails, and the rebuild in
    `core/duckdb_session.py` can be retired (with this test).
    """
    package, ids = package
    dbfile = package / "fichero.duckdb"
    duckdb.connect(str(dbfile)).close()  # replays the WAL, then checkpoints on close
    found, there = _index_misses(dbfile, "segment_passes", "document_id", ids["doc"])
    assert there == 1
    assert found == 0, "DuckDB no longer loses replayed rows from its indexes: retire the #5644 rebuild"


def test_a_pages_segments_are_listed_after_the_engine_was_killed(package, app_db):
    """`source.store.saved-is-found-after-a-crash`: the page's pass and its 85 lines, through the route."""
    package, ids = package
    db_manager.get_database(package)  # the next engine opens the library
    db_manager.close_all()  # ...and closes it cleanly: the checkpoint that used to write stale indexes
    try:
        body = _client(package, app_db).get(f"/api/segments/document/{ids['doc']}").json()
    finally:
        from fichero_server.api.main import app

        app.dependency_overrides.clear()
    assert [p["id"] for p in body["passes"]] == [ids["pass"]]
    assert len(body["segments"]) == 85
    for table, column, value, rows in (
        ("segment_passes", "document_id", ids["doc"], 1),
        ("segments", "pass_id", ids["pass"], 85),
        ("activities", "thread_id", ids["thread"], 40),
    ):
        db_manager.close_all()
        assert _index_misses(package / "fichero.duckdb", table, column, value) == (rows, rows), table


def test_a_failed_run_can_be_deleted_after_the_engine_was_killed(package, app_db):
    """`activity.durable.run-deletable-after-a-crash`: deleting it used to be the FATAL that shut the database.

    Starts where the maintainer's library was: the replay already checkpointed (indexes stale on disk)
    and no repair yet. The delete appends to the run's log, which DuckDB does as delete-then-insert
    through every index -- "Failed to delete all rows from index" on a stale one.
    """
    package, ids = package
    _damage_as_before_the_fix(package / "fichero.duckdb")
    from fichero_server.api.main import app

    try:
        client = _client(package, app_db)
        deleted = client.post("/api/workflow-execution/runs/delete", json={"thread_ids": [ids["thread"]]})
        assert deleted.status_code == 200, deleted.text
        assert ids["thread"] in json.dumps(deleted.json())
        runs = client.get("/api/workflow-execution/runs").json()
        assert ids["thread"] not in json.dumps(runs)
        # The database is still usable: the FATAL invalidated it for the whole session.
        assert client.get(f"/api/segments/document/{ids['doc']}").status_code == 200
    finally:
        app.dependency_overrides.clear()


def test_a_library_damaged_before_the_fix_is_repaired_once(package, caplog):
    """A library whose indexes were already written stale opens repaired, and the repair is not repeated."""
    package, ids = package
    dbfile = package / "fichero.duckdb"
    _damage_as_before_the_fix(dbfile)
    assert _index_misses(dbfile, "segment_passes", "document_id", ids["doc"]) == (0, 1)

    with caplog.at_level(logging.WARNING, logger="fichero_server.db"):
        Database(dbfile).close()
    assert "one-time repair" in caplog.text
    assert _index_misses(dbfile, "segment_passes", "document_id", ids["doc"]) == (1, 1)

    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="fichero_server.db"):
        Database(dbfile).close()
    assert "rebuilt" not in caplog.text, "a repaired library with a clean close is not rebuilt again"


def test_a_new_library_opens_without_rebuilding(tmp_path, caplog):
    """A clean, repaired library pays nothing at open: no WAL left behind, the repair recorded."""
    dbfile = tmp_path / "New.fichero" / "fichero.duckdb"
    dbfile.parent.mkdir()
    Database(dbfile).close()
    Database(dbfile).close()  # the first open made the settings table; this one records the repair
    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="fichero_server.db"):
        Database(dbfile).close()
    assert "rebuilt" not in caplog.text
    assert not Path(f"{dbfile}.wal").exists()


# --- Every other opener (#5644 sweep): the rebuild lives in `connect_utc`, which every DuckDB open in
# the engine goes through, so the first opener after a crash -- whoever it is -- gets sound indexes.

_PLAIN_CHILD = r"""
import duckdb, os, signal, sys, uuid
conn = duckdb.connect(sys.argv[1])
for i in range(3000):
    conn.execute("INSERT INTO t VALUES (?, ?)", [uuid.uuid4().hex, f"key{i % 10}"])
os.kill(os.getpid(), signal.SIGKILL)
"""


def _crash_plain_file(dbfile: Path) -> None:
    conn = duckdb.connect(str(dbfile))
    conn.execute("CREATE TABLE t (id VARCHAR PRIMARY KEY, k VARCHAR)")
    conn.execute("CREATE INDEX idx_t_k ON t (k)")
    conn.close()
    out = subprocess.run([sys.executable, "-c", _PLAIN_CHILD, str(dbfile)], capture_output=True, timeout=120)
    assert out.returncode == -9 and Path(f"{dbfile}.wal").exists()


def _index_agrees(dbfile: Path) -> bool:
    conn = duckdb.connect(str(dbfile))
    try:
        return all(
            conn.execute("SELECT count(*) FROM t WHERE k = ?", [k]).fetchone()[0]
            == conn.execute("SELECT count(*) FROM t WHERE k || '' = ?", [k]).fetchone()[0]
            for (k,) in conn.execute("SELECT DISTINCT k FROM t").fetchall()
        )
    finally:
        conn.close()


def test_any_first_opener_rebuilds_after_a_crash(tmp_path, monkeypatch):
    """Not only the library: whatever opens a crashed DuckDB file first through `connect_utc`."""
    from fichero_server.core import duckdb_session

    monkeypatch.setattr(duckdb_session, "_opened_in_this_process", set())
    dbfile = tmp_path / "any.duckdb"
    _crash_plain_file(dbfile)
    duckdb_session.connect_utc(str(dbfile)).close()  # replay; the close checkpoints
    assert _index_agrees(dbfile)


def test_the_activity_store_opening_first_finds_a_crashed_runs_rows(package, monkeypatch):
    """The activity store can open a library before its `Database` does; its rows are still found."""
    from fichero_server.core import duckdb_session
    from fichero_server.workflows.activity_store import ActivityStore

    monkeypatch.setattr(duckdb_session, "_opened_in_this_process", set())
    package, ids = package
    dbfile = package / "fichero.duckdb"
    store = ActivityStore(str(dbfile))
    assert store.delete_workflow_runs_sync([ids["thread"]]) == [ids["thread"]]
    db_manager.close_all()
    assert _index_misses(dbfile, "activities", "thread_id", ids["thread"]) == (40, 40)


def test_every_engine_open_goes_through_connect_utc():
    """The rebuild lives in `connect_utc`; a bare `duckdb.connect` elsewhere would skip it. A guard,
    beside the behaviour tests above, not instead of them."""
    import ast

    import fichero_server

    root = Path(fichero_server.__file__).parent
    bare = []
    for path in scan_rglob(root, "*.py"):
        if path.name == "duckdb_session.py":
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "connect"
                    and isinstance(node.func.value, ast.Name) and node.func.value.id == "duckdb"):
                bare.append(f"{path.relative_to(root)}:{node.lineno}")
    assert not bare, f"open DuckDB through core.duckdb_session.connect_utc (#5644): {bare}"
