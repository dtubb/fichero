"""#7088: the activity summary's model and place of a stage run are read with a narrow query that aggregates in the database,
so a run of many rows is answered under DuckDB's 256 MiB floor. The whole job tree, every row with its detail, ran out of
memory there ("failed to pin block"), and the run's Activity block had no model or place."""
from __future__ import annotations

import asyncio
import logging

ROWS = 20_000


def _a_run_of_many_rows(db):
    from fichero_server.execution import jobs

    jobs._ensure(db)
    db.execute("INSERT INTO jobs (id, kind, subject, state, attempts, created_at) VALUES ('w1', 'workflow', 's', 'running', 0, now())")
    # Each page's detail is about 19 KB (its usage, then what a page keeps): 380 MB in all, over the limit set below.
    db.execute(
        "INSERT INTO jobs (id, kind, subject, model, state, attempts, created_at, parent_id, detail) "
        "SELECT 'p' || i, 'transcribe', 'doc' || i, 'kraken:blla', 'done', 1, now(), 'w1', "
        "'{\"usage\": [{\"place\": \"this_mac\"}], \"pad\": \"' || repeat(md5(i::VARCHAR), 600) || '\"}' FROM range(?) t(i)", [ROWS])
    db.execute("SET memory_limit='256MiB'")


def test_the_summary_names_the_model_and_place_of_a_run_of_many_rows_under_the_memory_floor(db, monkeypatch, caplog):
    from fichero_server.api.routes.system import activity

    _a_run_of_many_rows(db)
    monkeypatch.setattr(activity, "_WHERE_AND_MODEL", {})
    with caplog.at_level(logging.WARNING, logger=activity.logger.name):
        answer = asyncio.run(activity._stage_where_and_model(db, "w1"))
    assert "no job rows" not in caplog.text, caplog.text[:400]
    assert answer == ("Kraken", "on this Mac")


def test_the_narrow_read_picks_the_running_rows_model_and_counts_each_place(db):
    from fichero_server.execution import jobs

    jobs._ensure(db)
    rows = [("w1", "workflow", None, "running", None, None),
            ("s1", "workflow-step", None, "running", "w1", None),
            ("a", "transcribe", "kraken:blla", "done", "s1", '{"usage": [{"place": "this_mac"}, {"place": "this_mac"}]}'),
            ("b", "transcribe", "gpt-4o", "running", "s1", '{"usage": [{"place": "provider"}, {}]}'),
            ("other", "transcribe", "qwen", "running", None, '{"usage": [{"place": "own_machine"}]}')]
    for i, (job_id, kind, model, state, parent, detail) in enumerate(rows):
        db.execute("INSERT INTO jobs (id, kind, subject, model, state, attempts, created_at, parent_id, detail) "
                   "VALUES (?, ?, 's', ?, ?, 0, now() + to_seconds(?), ?, ?)", [job_id, kind, model, state, i, parent, detail])
    assert jobs.model_and_places(db, "w1") == {"model": "gpt-4o", "state": "running", "places": {"this_mac": 2, "provider": 1}}
    db.execute("UPDATE jobs SET state = 'done' WHERE id = 'b'")
    assert jobs.model_and_places(db, "w1")["model"] == "gpt-4o", "no row running: the last row that names a model"
    assert jobs.model_and_places(db, "s1")["places"] == {"this_mac": 2, "provider": 1}
    assert jobs.model_and_places(db, "nothing") is None
