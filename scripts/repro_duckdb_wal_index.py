#!/usr/bin/env python3
"""DuckDB writes stale secondary indexes at the first checkpoint after replaying a WAL (#5644).

One table, one index, one writer killed mid-write; open and close (replay + checkpoint); reopen and
compare each key's count through the index with a table scan. Measured 2026-10-09: 1.3.2 clean;
1.4.4, 1.5.0, 1.5.3, 1.5.5, 1.5.6 wrong for every key, every run. The engine's workaround is
`fichero_server.core.duckdb_session.rebuild_secondary_indexes`; when this prints "clean" on the
bundled DuckDB, the workaround can go.

    python scripts/repro_duckdb_wal_index.py [scratch_dir]
"""

import os
import signal
import subprocess
import sys
import tempfile
import uuid

import duckdb

if len(sys.argv) > 2 and sys.argv[2] == "child":
    conn = duckdb.connect(sys.argv[1])
    for i in range(5000):
        conn.execute("INSERT INTO t VALUES (?, ?)", [uuid.uuid4().hex, f"key{i % 10}"])
    os.kill(os.getpid(), signal.SIGKILL)

path = os.path.join(sys.argv[1] if len(sys.argv) > 1 else tempfile.mkdtemp(), "repro.duckdb")
for f in (path, path + ".wal"):
    if os.path.exists(f):
        os.remove(f)
conn = duckdb.connect(path)
conn.execute("CREATE TABLE t (id VARCHAR PRIMARY KEY, k VARCHAR)")
conn.execute("CREATE INDEX idx_t_k ON t (k)")
conn.close()
subprocess.run([sys.executable, __file__, path, "child"])
duckdb.connect(path).close()  # replay the WAL; the close checkpoints
conn = duckdb.connect(path)
wrong = [k for (k,) in conn.execute("SELECT DISTINCT k FROM t").fetchall()
         if conn.execute("SELECT count(*) FROM t WHERE k = ?", [k]).fetchone()[0]
         != conn.execute("SELECT count(*) FROM t WHERE k || '' = ?", [k]).fetchone()[0]]
print(f"duckdb {duckdb.__version__}: " + (f"{len(wrong)} of 10 keys wrong through the index" if wrong else "clean"))
sys.exit(1 if wrong else 0)
