"""A run that ended interrupted says why in its row (`activity.pane.failure-with-its-fix-in-the-row`, #6588, #6596).

Seen in the Dev Local build, 2026-11-14 night: a Kraken run the project's close interrupted was listed `failed` with no
`failure`, so its row showed a red X and no words (its reason is a sentence, past the row's eight words). The listed run
now carries the `interrupted` kind: its row words, its fix and Retry.
"""
from __future__ import annotations

from fichero_server.llm import failure
from tests.unit.api.test_routes_workflow_execution import _seed_run


def test_the_interrupted_kind_has_short_words_a_fix_and_retry():
    built = failure.of_kind("interrupted")
    assert failure.row_words("interrupted") == "Stopped before it finished"
    assert built.fix and [a.kind for a in built.actions] == ["retry"]


def test_a_listed_interrupted_run_carries_its_failure(client, db):
    import asyncio

    tracker = _seed_run(db, "thread-interrupted", status="failed")
    asyncio.run(tracker.store.update_workflow_run(
        "thread-interrupted", error="Interrupted: the project was closed at 22:58, before this run finished"))
    rows = {j["id"]: j for j in client.get("/api/activity/jobs").json()["jobs"]}
    row = rows["thread-interrupted"]
    assert row["failure"]["kind"] == "interrupted"
    assert row["failure"]["row_words"] == "Stopped before it finished"
