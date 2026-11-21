"""Perf case: the neighbourhood of a name at project size (kg.scale.ratchet-at-project-size).

``GET /api/kg/graph/neighborhood/{id}`` for a name on thousands of statements, in a library of
5,000 pages / 50,000 statements / 12,500 names (``_kg_project_size``). Report-only: the time goes
to the perf ratchet's history and is printed; no ceiling is asserted until the store spec's
Step 2.4 (the neighbourhood as a join) lands and a baseline is set with FICHERO_PERF_TIGHTEN=1.

NOT part of the unit gate. Run explicitly:

    uv run pytest tests/perf/test_kg_neighbourhood_perf.py -q -s
"""

from __future__ import annotations

import sys as _sys
import time
from pathlib import Path as _Path

_sys.path.insert(0, str(_Path(__file__).resolve().parent))
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))
from _kg_project_size import N_CLAIMS, seed_project_size  # noqa: E402
from perf_ratchet import record  # noqa: E402


def test_neighbourhood_of_a_busy_name_at_project_size(client, db):
    ids = seed_project_size(db)
    start = time.perf_counter()
    r = client.get(f"/api/kg/graph/neighborhood/{ids['hot_entity_id']}")
    ms = (time.perf_counter() - start) * 1000
    assert r.status_code == 200, r.text
    assert r.json()["edges"], "the busy name should have edges in a seeded library"
    print(f"\n[perf] kg neighbourhood ({N_CLAIMS} statements, busy name): {ms:.1f} ms")
    record("kg.neighbourhood.project_size", ms)
