"""What can we do with this many pages? Routes side by side, every figure saying where it came from.

WHY (`source.onboard.routes-for-the-volume`, ruled 2026-10-03): a historian with X pages chooses
between reading it all in the cloud, reading it on this Mac, and distilling a small model first.
The choice is only honest if each number says whether it was measured here, is an estimate, or is
unknown -- a guessed time or accuracy shown as fact would steer someone into days of wasted work.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fichero_server.execution import jobs
from fichero_server.recipes.routes import measured_seconds_per_page, routes_for_volume

KRAKEN = "kraken:kraken-zenodo-21788410"
GEMINI = "openrouter/google/gemini-3-flash-preview"


def _finished(db, model, seconds, n):
    jobs._ensure(db)
    t0 = datetime(2026, 10, 3, tzinfo=timezone.utc)
    for i in range(n):
        db.execute("INSERT INTO jobs (id, kind, subject, model, state, created_at, started_at, finished_at) "
                   "VALUES (?, 'find-lines', ?, ?, 'done', ?, ?, ?)",
                   [f"j{model}{i}", f"p{i}", model, t0, t0, t0 + timedelta(seconds=seconds[i % len(seconds)])])


def test_speed_is_the_median_of_this_macs_finished_pages(db):
    _finished(db, KRAKEN, [20, 25, 400], 3)  # one slow outlier does not set the speed
    assert measured_seconds_per_page(db, KRAKEN) == 25
    assert measured_seconds_per_page(db, "kraken:never-ran") is None


def test_three_routes_each_figure_naming_its_basis(db):
    _finished(db, KRAKEN, [25], 5)
    cloud, mac, distil = routes_for_volume(db, 1000, teacher=GEMINI, local_reader=KRAKEN, sample_pages=300)

    assert [cloud["id"], mac["id"], distil["id"]] == ["cloud", "this-mac", "distil"]
    assert cloud["cost_usd"]["basis"] == "estimate" and cloud["cost_usd"]["value"] > 0
    assert cloud["time_seconds"] == {"value": None, "basis": "unknown", "from": cloud["time_seconds"]["from"]}
    assert mac["cost_usd"]["value"] == 0 and mac["time_seconds"] == {
        "value": 25_000, "basis": "measured", "from": mac["time_seconds"]["from"]}
    label, train, read = distil["steps"]
    assert label["pages"] == 300 and label["cost_usd"]["value"] < cloud["cost_usd"]["value"]
    assert train["time_seconds"]["basis"] == "unknown"  # no training run measured: never invented
    assert read["time_seconds"]["value"] == 25_000
    assert all(r["accuracy_cer"]["basis"] == "unknown" for r in (cloud, mac, distil))
    assert (cloud["leaves_this_mac"], mac["leaves_this_mac"]) == (True, False)


def test_an_unmeasured_reader_is_unknown_not_zero(db):
    mac = routes_for_volume(db, 50, teacher=GEMINI, local_reader="kraken:never-ran", sample_pages=10)[1]
    assert mac["time_seconds"]["value"] is None and mac["time_seconds"]["basis"] == "unknown"


def test_the_route_serves_the_routes(client, db):
    _finished(db, KRAKEN, [30], 3)
    r = client.get("/api/recipes/routes", params={"teacher": GEMINI, "local_reader": KRAKEN, "pages": 100})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pages"] == 100 and body["routes"][1]["time_seconds"]["value"] == 3000
    assert body["routes"][1]["time_seconds"]["from"]  # the basis travels under its own name
    assert client.get("/api/recipes/routes", params={"teacher": GEMINI, "local_reader": KRAKEN,
                                                     "pages": 5, "sample_pages": 0}).status_code == 422
