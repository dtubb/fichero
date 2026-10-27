"""Dogfood 2026-10-27: a Find Lines stage said "Finding regions: 0 of 1 pages". A find-lines step runs the shipped
Detect Segments (Kraken) workflow, whose node runs the recipe's region loop one page at a time (`detect_regions`,
elementwise); that loop's words reached the run as the find-lines stage's line."""
# ruff: noqa: F811 -- pytest fixtures imported from the sibling tests are named as test arguments
from __future__ import annotations

import time

from tests.unit.recipes.test_recipe_execution_to_spec import (  # noqa: F401  (fixtures)
    _finished,
    _recipe,
    _run_status,
    _save,
    _start,
    engine,
    pages,
)

STEPS = [{"id": "regions", "job": "find-regions", "model": {"kraken": "blla", "kraken_version": "bundled"}},
         {"id": "lines", "job": "find-lines", "model": {"kraken": "blla", "kraken_version": "bundled"}}]


def test_a_find_lines_stage_never_says_finding_regions(client, db, pages, tmp_path, engine, monkeypatch):
    """Find Regions then Find Lines on two pages: while Find Lines runs, neither the run's line nor any row under it
    says "Finding regions", nor counts "of 1 page"."""
    from fichero_server.llm import kraken_runtime

    segment = kraken_runtime.segment_lines

    def slow_segment(image_path, **kw):  # long enough for the status to be read while each page is segmented
        time.sleep(0.5)
        return segment(image_path, **kw)

    monkeypatch.setattr(kraken_runtime, "segment_lines", slow_segment)
    _save(client, _recipe(tmp_path, *STEPS))
    run_id = _start(client)
    said: set[str] = set()
    while (status := _run_status(client, run_id))["state"] not in ("done", "failed", "cancelled"):
        if any("lines" in s["steps"] and s["state"] == "running" for s in status["steps"]):
            said.add(status.get("reason") or "")
            said.update(r for (r,) in db.execute_fetchall("SELECT reason FROM jobs WHERE reason IS NOT NULL"))
        time.sleep(0.05)
    assert status["state"] == "done", status
    assert any(r.startswith("Finding the lines") for r in said), said
    assert not [r for r in said if "Finding regions" in r or "of 1 page" in r], said
