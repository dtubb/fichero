"""Perf case: the cold directed graph build at project size (kg.scale.ratchet-at-project-size).

``build_full_graph`` with its cache dropped first, in a library of 5,000 pages / 50,000
statements / 12,500 names (``_kg_project_size``); every statement carries a verb and an object
naming another entity, so each one becomes an edge. Report-only: the time goes to the perf
ratchet's history and is printed; no ceiling is asserted until the store spec's Step 3.3 (the
cached graph built from rows) lands and a baseline is set with FICHERO_PERF_TIGHTEN=1.

NOT part of the unit gate. Run explicitly:

    uv run pytest tests/perf/test_kg_graph_build_perf.py -q -s
"""

from __future__ import annotations

import sys as _sys
import time
from pathlib import Path as _Path

_sys.path.insert(0, str(_Path(__file__).resolve().parent))
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))
from _kg_project_size import N_CLAIMS, N_ENTITIES, seed_project_size  # noqa: E402
from perf_ratchet import record  # noqa: E402

from fichero_server.knowledge.graph import build_full_graph, invalidate_graph_cache


def test_cold_graph_build_at_project_size(db):
    seed_project_size(db)
    invalidate_graph_cache(db)
    start = time.perf_counter()
    graph = build_full_graph(db)
    ms = (time.perf_counter() - start) * 1000
    assert graph.number_of_nodes() >= N_ENTITIES
    assert graph.number_of_edges() >= N_CLAIMS
    print(f"\n[perf] kg graph build, cold ({N_CLAIMS} statements): {ms:.1f} ms")
    record("kg.graph_build.project_size", ms)
