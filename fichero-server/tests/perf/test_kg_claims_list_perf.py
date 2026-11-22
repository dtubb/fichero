"""Perf case: the statements list and the two count routes at project size (kg.scale.ratchet-at-project-size).

One library at 5,000 pages / 50,000 statements / 12,500 names (``_kg_project_size``), then
``GET /api/claims?limit=200``, ``GET /api/entities/top`` and ``GET /api/entities/claim-counts``.
Report-only: each time goes to the perf ratchet's history and is printed; no ceiling is
asserted until the store spec's Steps 2.2 and 2.3 land and a baseline is set with
FICHERO_PERF_TIGHTEN=1.

NOT part of the unit gate. Run explicitly:

    uv run pytest tests/perf/test_kg_claims_list_perf.py -q -s
"""

from __future__ import annotations

import sys as _sys
import time
from pathlib import Path as _Path

_sys.path.insert(0, str(_Path(__file__).resolve().parent))
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))
from _kg_project_size import N_CLAIMS, seed_project_size  # noqa: E402
from perf_ratchet import record  # noqa: E402


def test_claims_list_and_counts_at_project_size(client, db):
    ids = seed_project_size(db)
    for name, path in (
        ("kg.claims.list.project_size", "/api/claims?limit=200"),
        ("kg.entities.top.project_size", "/api/entities/top"),
        ("kg.entities.claim_counts.project_size", "/api/entities/claim-counts"),
    ):
        start = time.perf_counter()
        r = client.get(path)
        ms = (time.perf_counter() - start) * 1000
        assert r.status_code == 200, f"{path}: {r.text}"
        body = r.json()
        if "counts" in body:
            assert body["counts"][ids["hot_entity_id"]] > 0
        else:
            assert body["items"], f"{path} answered no rows in a seeded library"
        print(f"\n[perf] {path} ({N_CLAIMS} statements): {ms:.1f} ms")
        record(name, ms)
