"""Owner 2026-11-28: the builder's history over all time, from an incremental DuckDB index of the journals; nothing is dropped."""
from __future__ import annotations

import json
import time

import pytest

pytest.importorskip("duckdb")

from fichero_builder import history, journal  # noqa: E402


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setattr(journal, "STATE", tmp_path / "s")
    (tmp_path / "s").mkdir()
    monkeypatch.setattr(history, "_CONN", {})
    yield tmp_path
    for c in history._CONN.values():
        c.close()


def put(p, *rows):
    with p.open("a") as f:
        for r in rows:
            f.write((r if isinstance(r, str) else json.dumps(r)) + "\n")


def count(sql="SELECT count(*) n FROM rows"):
    return history.query(sql)[0]["n"]


def test_a_pass_adds_exactly_the_new_rows_and_a_half_written_line_waits(state):
    put(journal.path(), {"ts": "2026-10-01T10:00:00", "event": "landed", "lane": "a", "step": "done", "sha": "x"},
        {"ts": "2026-10-01T11:00:00", "event": "check", "ok": True, "seconds": 12.5}, "not json", '["a list"]')
    assert history.update() == 2 and count() == 2, "a line that does not parse, or is not an object, is skipped"
    assert history.update() == 0, "nothing new"
    with journal.path().open("a") as f:
        f.write('{"ts": "2026-11-28T09:00:00", "event": "alert", "id": "a-1", "lane": "l"')
    assert history.update() == 0, "a line being written waits"
    with journal.path().open("a") as f:
        f.write("}\n")
    assert history.update() == 1
    r = history.query("SELECT lane, step, sha, day::VARCHAR d FROM landed")[0]
    assert r == {"lane": "a", "step": "done", "sha": "x", "d": "2026-10-01"}
    assert history.query("SELECT seconds FROM checks")[0]["seconds"] == 12.5
    assert json.loads(history.query("SELECT raw FROM alerts")[0]["raw"])["id"] == "a-1", "the whole row is kept"


def test_a_file_rewritten_or_replaced_is_indexed_again_from_the_start(state):
    put(journal.path(), {"ts": "2026-11-01T00:00:00", "event": "check", "state": "a"}, {"ts": "2026-11-01T00:00:01", "event": "check", "state": "b"})
    history.update()
    journal.path().write_text(json.dumps({"ts": "2026-11-02T00:00:00", "event": "check", "state": "c"}) + "\n")
    history.update()
    assert [r["state"] for r in history.query("SELECT state FROM rows ORDER BY ts")] == ["c"]


def test_the_workers_journal_gives_only_its_run_rows_and_names_the_lane(state):
    wr = state / "wr"
    (wr / "state").mkdir(parents=True)
    (state / "root").mkdir()
    (state / "root" / "harness.toml").write_text(f'[jail]\nworkroot = "{wr}"\n')
    put(wr / "state" / "journal.jsonl", {"ts": "2026-11-28T08:00:00", "event": "cost", "task": "seg", "usd": 1.25, "model": "sonnet"},
        {"ts": "2026-11-28T08:00:01", "event": "landed", "lane": "forged"})
    history.update(state / "root")
    assert history.query("SELECT lane, usd, model, source FROM rows") == [{"lane": "seg", "usd": 1.25, "model": "sonnet", "source": "worker"}]


def test_an_index_of_the_archive_months_and_the_hot_file_equals_one_of_the_single_file(state, tmp_path, monkeypatch):
    rows = [{"ts": f"2026-{m:02d}-{d:02d}T10:00:00", "event": "landed", "lane": "l", "step": "done", "n": m * 100 + d}
            for m in (9, 10, 11) for d in (1, 15)]
    put(journal.path(), *rows)
    history.update()
    whole = history.query("SELECT raw FROM rows ORDER BY ts")
    for c in history._CONN.values():
        c.close()
    monkeypatch.setattr(history, "_CONN", {})
    monkeypatch.setattr(journal, "STATE", tmp_path / "split")
    (tmp_path / "split" / "archive").mkdir(parents=True)
    put(tmp_path / "split" / "archive" / "journal-2026-09.jsonl", *rows[:2])
    put(tmp_path / "split" / "archive" / "journal-2026-10.jsonl", *rows[2:4])
    put(journal.path(), *rows[4:])
    history.update()
    assert history.query("SELECT raw FROM rows ORDER BY ts") == whole


def test_two_hundred_thousand_rows_index_once_then_a_pass_and_a_history_query_are_quick(state):
    with journal.path().open("w") as f:
        for i in range(200_000):
            day = 1 + i % 28
            f.write(json.dumps({"ts": f"2026-{10 + i % 2}-{day:02d}T10:{i % 60:02d}:00", "event": ("landed", "check", "alert", "cost")[i % 4],
                                "lane": f"l{i % 9}", "step": "done", "ok": True, "seconds": i % 300, "usd": 0.5, "detail": "x" * 200}) + "\n")
    t = time.time()
    assert history.update() == 200_000
    first = time.time() - t
    put(journal.path(), {"ts": "2026-11-28T12:00:00", "event": "check", "ok": False})
    t = time.time()
    assert history.update() == 1
    assert time.time() - t < 0.2 + 0.5, "a pass reads only the new bytes"  # ponytail: slack for a loaded runner
    t = time.time()
    per_day = history.query("SELECT day, count(*) n FROM landed WHERE step = 'done' GROUP BY day ORDER BY day")
    assert time.time() - t < 0.2 + 0.3 and sum(r["n"] for r in per_day) == 50_000
    assert first < 60, f"the first build took {first:.1f} s"


def _seventy_days(state):
    import datetime
    rows = []
    start = datetime.date(2026, 9, 20)
    for i in range(70):
        d = (start + datetime.timedelta(days=i)).isoformat()
        rows += [{"ts": f"{d}T10:00:00", "event": "landed", "lane": "seg", "step": "done", "sha": f"s{i}"},
                 {"ts": f"{d}T10:05:00", "event": "check", "ok": i % 5 != 0},
                 {"ts": f"{d}T10:06:00", "event": "activity", "state": "rung", "rung": "unit", "seconds": 60 + i, "ok": True},
                 {"ts": f"{d}T10:07:00", "event": "alert", "id": f"a-{i}", "lane": "seg", "what": f"sent {i} h ago with no word; more"}]
    put(journal.path(), *rows)
    wr = state / "wr"
    (wr / "state").mkdir(parents=True)
    (state / "root").mkdir()
    (state / "root" / "harness.toml").write_text(f'[jail]\nworkroot = "{wr}"\n')
    put(wr / "state" / "journal.jsonl", *({"ts": f"{(start + datetime.timedelta(days=i)).isoformat()}T11:00:00", "event": "cost", "task": "seg",
                                            "model": "sonnet" if i % 2 else "opus", "usd": 2.0} for i in range(70)))
    history.update(state / "root")
    return (start + datetime.timedelta(days=69)).isoformat()


def test_the_history_views_cover_30_days_90_days_and_all_time(state):
    """builder-console.history.all-time-index: landings, cost by model, checks, alerts by kind, rungs and lanes over each range."""
    today = _seventy_days(state)
    v30, v90, va = (history.views(r, today) for r in ("30", "90", "all"))
    assert len(v30["buckets"]) == 30 and v30["buckets"][-1] == today and sum(v30["landings"]) == 30
    assert len(v90["buckets"]) == 70 and sum(v90["landings"]) == 70, "90 days holds every one of the 70"
    assert va["unit"] == "week" and sum(va["landings"]) == 70 and len(va["buckets"]) == 11, "All, a week a bucket"
    assert sum(v90["cost"]["sonnet"]) + sum(v90["cost"]["opus"]) == 140.0, "the worker's cost rows, by model"
    assert sum(v90["checks"]["red"]) == 14 and sum(v90["checks"]["green"]) == 56
    assert list(v90["alerts"]) == ["sent N h ago with no word"] and sum(v90["alerts"]["sent N h ago with no word"]) == 70
    (r,) = v90["rungs"]
    assert r["rung"] == "unit" and r["n"] == 70 and r["red_pct"] == 0
    (lane,) = va["lanes"]
    assert lane == {"lane": "seg", "landings": 70, "usd": 140.0, "reds": 0}


def test_the_history_endpoint_answers_each_range_and_the_page_offers_them(state, monkeypatch):
    import threading
    import urllib.request

    from fichero_builder import console
    _seventy_days(state)
    monkeypatch.setattr(console, "ROOT", state / "root")
    srv = console.server("127.0.0.1", 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{srv.server_address[1]}/api/history"
        for rng, unit in (("30", "day"), ("90", "day"), ("all", "week"), ("nonsense", "day")):
            t = time.time()
            got = json.loads(urllib.request.urlopen(f"{url}?range={rng}", timeout=10).read())
            assert got["unit"] == unit and time.time() - t < 1.0
    finally:
        srv.shutdown()
    page = console.PAGE.read_text()
    assert '["history", "History"]' in page and '[["30", "30 days"], ["90", "90 days"], ["all", "All"]]' in page and 'useState("30")' in page
