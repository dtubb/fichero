"""The builder's history index (owner 2026-11-28: the console shows the builder's history over all time): every journal row, the
owner's and the worker's run rows, in one DuckDB table `rows` with its common fields and the whole row as JSON, plus one view per
kind. Built incrementally: each pass reads only the bytes appended to each source file since the last one (a file replaced, shorter,
or with other first bytes is indexed again from the start). Nothing is ever dropped. One process writes it (the console); a CLI
reader asks the console's API or opens the file read-only. duckdb is imported lazily: the builder itself stays stdlib-only."""
from __future__ import annotations

import os
import tempfile
import threading
import tomllib
from pathlib import Path

from fichero_builder import journal

WORKER_ROWS = ("worker", "cost", "reading")  # from the worker's shared journal only these count (as console.rows_of)
_LOCK = threading.Lock()
_CONN: dict = {}  # path -> connection (one writer, this process)

SCHEMA = """
CREATE TABLE IF NOT EXISTS rows (ts TIMESTAMP, day DATE, event VARCHAR, lane VARCHAR, step VARCHAR, state VARCHAR, id VARCHAR,
  sha VARCHAR, ok BOOLEAN, usd DOUBLE, seconds DOUBLE, runner VARCHAR, model VARCHAR, source VARCHAR, file VARCHAR, raw JSON);
CREATE TABLE IF NOT EXISTS meta (file VARCHAR PRIMARY KEY, ino BIGINT, off BIGINT, head BLOB);
CREATE OR REPLACE VIEW landed AS SELECT * FROM rows WHERE event = 'landed';
CREATE OR REPLACE VIEW checks AS SELECT * FROM rows WHERE event = 'check';
CREATE OR REPLACE VIEW trains AS SELECT * FROM rows WHERE event = 'train';
CREATE OR REPLACE VIEW costs AS SELECT * FROM rows WHERE event = 'cost';
CREATE OR REPLACE VIEW alerts AS SELECT * FROM rows WHERE event = 'alert';
CREATE OR REPLACE VIEW alert_answers AS SELECT * FROM rows WHERE event = 'alert-answer';
CREATE OR REPLACE VIEW queue_states AS SELECT * FROM rows WHERE event = 'queue';
"""

# the common fields, read from each row's JSON; `task` is a worker row's lane
FIELDS = """TRY_CAST(json->>'ts' AS TIMESTAMP), TRY_CAST(TRY_CAST(json->>'ts' AS TIMESTAMP) AS DATE), json->>'event',
  COALESCE(json->>'lane', json->>'task'), json->>'step', json->>'state', json->>'id', json->>'sha', TRY_CAST(json->>'ok' AS BOOLEAN),
  TRY_CAST(json->>'usd' AS DOUBLE), TRY_CAST(json->>'seconds' AS DOUBLE), json->>'runner', json->>'model'"""


def db_path() -> Path:
    return journal.STATE / "history.duckdb"


def connect(read_only: bool = False):
    import duckdb
    p = db_path()
    if read_only:
        return duckdb.connect(str(p), read_only=True)
    c = _CONN.get(str(p))
    if c is None:
        p.parent.mkdir(parents=True, exist_ok=True)
        c = _CONN[str(p)] = duckdb.connect(str(p))
        c.execute(SCHEMA)
    return c


def sources(root=None) -> list[tuple[Path, str]]:
    """(file, source) to index: the archive months (a rotation's), the owner's journal, and the worker's shared one."""
    out = [(f, "owner") for f in sorted((journal.STATE / "archive").glob("journal-[0-9][0-9][0-9][0-9]-[0-9][0-9].jsonl"))]
    out.append((journal.path(), "owner"))
    f = Path(root) / "harness.toml" if root else None
    workroot = tomllib.loads(f.read_text()).get("jail", {}).get("workroot") if f and f.is_file() else None
    shared = Path(workroot) / "state" / "journal.jsonl" if workroot else None
    if shared and shared.is_file() and shared.resolve() != journal.path().resolve():
        out.append((shared, "worker"))
    return out


def update(root=None) -> int:
    """One incremental pass over every source; the rows added."""
    added = 0
    with _LOCK:
        c = connect()
        for f, source in sources(root):
            try:
                st = f.stat()
            except OSError:
                continue
            m = c.execute("SELECT ino, off, head FROM meta WHERE file = ?", [str(f)]).fetchone()
            with f.open("rb") as fh:
                head = fh.read(256)
                if m is None or m[0] != st.st_ino or st.st_size < m[1] or not head.startswith(bytes(m[2])[: len(head)]) or len(head) < len(m[2]):
                    c.execute("DELETE FROM rows WHERE file = ?", [str(f)])
                    m = (st.st_ino, 0, head)
                if st.st_size <= m[1]:
                    continue
                fh.seek(m[1])
                chunk = fh.read(st.st_size - m[1])
            end = chunk.rfind(b"\n") + 1  # whole lines only: a line being written waits for the next pass
            if not end:
                continue
            with tempfile.NamedTemporaryFile("wb", suffix=".jsonl", delete=False) as t:
                t.write(chunk[:end])
            try:
                where = f"WHERE json->>'event' IN ({', '.join(repr(e) for e in WORKER_ROWS)})" if source == "worker" else ""
                n0 = c.execute("SELECT count(*) FROM rows").fetchone()[0]
                c.execute("BEGIN")
                c.execute(f"INSERT INTO rows SELECT {FIELDS}, ?, ?, json FROM read_ndjson_objects(?, ignore_errors = true) "
                          f"{'WHERE' if not where else where + ' AND'} json_valid(json) AND json_type(json) = 'OBJECT'",
                          [source, str(f), t.name])
                c.execute("INSERT OR REPLACE INTO meta VALUES (?, ?, ?, ?)", [str(f), st.st_ino, m[1] + end, head])
                c.execute("COMMIT")
                added += c.execute("SELECT count(*) FROM rows").fetchone()[0] - n0
            except Exception:
                c.execute("ROLLBACK")
                raise
            finally:
                os.unlink(t.name)
    return added


def query(sql: str, params: list | None = None) -> list[dict]:
    """A read of the index as dicts (the console's history endpoints)."""
    with _LOCK:
        cur = connect().execute(sql, params or [])
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]
