"""W3 search (#6600 Step 3): 200 queries from a committed list over a seeded library, text only (a semantic query needs a model,
and a perf test never fetches one). `perf-sweep.workload.set`."""

from __future__ import annotations

import sys as _sys
import time
from pathlib import Path as _Path

_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))
from perf_ratchet import record  # noqa: E402

from fichero_server.models import DocType, Document  # noqa: E402

QUERIES = (_Path(__file__).resolve().parents[3] / "scripts" / "perf_search_queries.txt").read_text().splitlines()
N_DOCS = 200
TOTAL_BUDGET_S = 60.0


def test_two_hundred_text_queries(client, db, tmp_path, monkeypatch):
    # a gate box roots pytest's tmp outside every default allowed location: allow this test's own dir, as the engine's server deployments do
    monkeypatch.setenv("FICHERO_LIBRARY_ALLOWED_ROOTS", str(tmp_path))
    words = "ledger harbour letter garden river market bell church field mill".split()
    assert db.save_many([Document(name=f"{words[i % len(words)]} {i:04d}.jpg", doc_type=DocType.file) for i in range(N_DOCS)]) == N_DOCS
    assert len(QUERIES) == 200
    start = time.perf_counter()
    for q in QUERIES:
        r = client.post("/api/search", json={"query": q, "limit": 10, "include": ["content"], "search_type": "fulltext"})
        assert r.status_code == 200, (q, r.status_code, r.text[:200])
    elapsed = time.perf_counter() - start
    print(f"\n[perf] 200 text searches over {N_DOCS} docs: {elapsed * 1000:.0f} ms")
    record("search.200-queries", elapsed * 1000)
    assert elapsed < TOTAL_BUDGET_S
