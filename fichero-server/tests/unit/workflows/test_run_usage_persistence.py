"""A run's cost survives the round-trip to the database and back (2026-09-03).

Activity could report a run's duration to the millisecond and not a cent of
its cost, because nothing persisted what the run spent. These tests hold the
`run_usage` column to the contract the client reads it under: recorded on
every terminal path, null-not-zero when unpriced, and absent (not zero) for a
run that never called a model.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from fichero_server.llm.usage import aggregate_usage
from fichero_server.workflows.activity_store import ActivityStore


def _store(tmp_path: Path) -> ActivityStore:
    return ActivityStore(str(tmp_path / "activity.duckdb"))


async def _seed(store: ActivityStore, thread_id: str = "run-usage-1") -> str:
    await store.save_workflow_run(
        thread_id=thread_id,
        workflow_id="wf-usage",
        workflow_name="Usage Workflow",
        started_at=datetime(2026, 9, 3, 9, 0, tzinfo=timezone.utc),
    )
    return thread_id


@pytest.mark.asyncio
async def test_run_usage_round_trips(tmp_path: Path) -> None:
    store = _store(tmp_path)
    thread_id = await _seed(store)

    totals = aggregate_usage(
        [
            {
                "provider": "openai",
                "model": "gpt-4o",
                "input_tokens": 1000,
                "output_tokens": 200,
                "total_tokens": 1200,
            }
        ]
    )
    await store.update_workflow_run(
        thread_id=thread_id,
        status="completed",
        run_usage=totals.model_dump(exclude={"calls"}),
        completed_at=datetime(2026, 9, 3, 9, 1, tzinfo=timezone.utc),
    )

    run = await store.get_workflow_run(thread_id)
    assert run is not None
    assert run.run_usage is not None
    assert run.run_usage["model_calls"] == 1
    assert run.run_usage["total_tokens"] == 1200
    assert run.run_usage["priced"] is True
    assert run.run_usage["cost_usd"] > 0


@pytest.mark.asyncio
async def test_unpriced_run_persists_a_null_cost_not_a_zero(tmp_path: Path) -> None:
    store = _store(tmp_path)
    thread_id = await _seed(store, "run-usage-unpriced")

    totals = aggregate_usage(
        [{"provider": "openrouter", "model": "nobody-prices-this-x9", "input_tokens": 50}]
    )
    await store.update_workflow_run(
        thread_id=thread_id, status="completed", run_usage=totals.model_dump(exclude={"calls"})
    )

    run = await store.get_workflow_run(thread_id)
    assert run is not None and run.run_usage is not None
    assert run.run_usage["cost_usd"] is None
    assert run.run_usage["priced"] is False
    assert run.run_usage["unpriced_models"] == ["nobody-prices-this-x9"]


@pytest.mark.asyncio
async def test_run_that_called_no_model_records_no_usage(tmp_path: Path) -> None:
    # A conversion-only run spent nothing AND called nothing. The column stays
    # null so the client shows no cost line at all — rather than "$0.00",
    # which is a claim about model spending that never happened.
    store = _store(tmp_path)
    thread_id = await _seed(store, "run-usage-none")
    await store.update_workflow_run(thread_id=thread_id, status="completed")

    run = await store.get_workflow_run(thread_id)
    assert run is not None
    assert run.run_usage is None


@pytest.mark.asyncio
async def test_failed_run_still_records_what_it_spent(tmp_path: Path) -> None:
    # The side effect that matters most: a run that died halfway still billed.
    store = _store(tmp_path)
    thread_id = await _seed(store, "run-usage-failed")
    totals = aggregate_usage(
        [{"provider": "openai", "model": "gpt-4o", "input_tokens": 400, "output_tokens": 40}]
    )
    await store.update_workflow_run(
        thread_id=thread_id,
        status="failed",
        error="node blew up",
        run_usage=totals.model_dump(exclude={"calls"}),
    )

    run = await store.get_workflow_run(thread_id)
    assert run is not None and run.run_usage is not None
    assert run.status == "failed"
    assert run.run_usage["cost_usd"] > 0


@pytest.mark.asyncio
async def test_updating_other_fields_does_not_erase_recorded_usage(tmp_path: Path) -> None:
    store = _store(tmp_path)
    thread_id = await _seed(store, "run-usage-keep")
    totals = aggregate_usage(
        [{"provider": "openai", "model": "gpt-4o", "input_tokens": 100, "output_tokens": 10}]
    )
    await store.update_workflow_run(
        thread_id=thread_id, run_usage=totals.model_dump(exclude={"calls"})
    )
    # A later log flush must not blank the column (update builds its SET list
    # from the non-None arguments only).
    await store.update_workflow_run(thread_id=thread_id, execution_log="more log\n")

    run = await store.get_workflow_run(thread_id)
    assert run is not None and run.run_usage is not None
    assert run.run_usage["model_calls"] == 1


@pytest.mark.asyncio
async def test_list_workflow_runs_carries_usage(tmp_path: Path) -> None:
    store = _store(tmp_path)
    thread_id = await _seed(store, "run-usage-list")
    totals = aggregate_usage(
        [{"provider": "apple", "model": "apple-intelligence", "input_tokens": 10}]
    )
    await store.update_workflow_run(
        thread_id=thread_id, status="completed", run_usage=totals.model_dump(exclude={"calls"})
    )

    runs = await store.list_workflow_runs(workflow_id="wf-usage")
    assert runs and runs[0].run_usage is not None
    # On-device: a zero we can defend, flagged priced so the UI says "Free".
    assert runs[0].run_usage["cost_usd"] == 0.0
    assert runs[0].run_usage["priced"] is True


@pytest.mark.asyncio
async def test_estimated_cost_round_trips_and_pairs_with_actual(tmp_path: Path) -> None:
    # The calibration Daniel asked for: the estimate recorded at start survives
    # alongside the actual recorded at completion, so a run row carries
    # "est → actual" as one fact.
    store = _store(tmp_path)
    await store.save_workflow_run(
        thread_id="run-est-1",
        workflow_id="wf-usage",
        workflow_name="Usage Workflow",
        started_at=datetime(2026, 9, 5, 9, 0, tzinfo=timezone.utc),
        estimated_cost=0.42,
    )
    totals = aggregate_usage(
        [{"provider": "openai", "model": "gpt-4o", "input_tokens": 1000, "output_tokens": 200}]
    )
    await store.update_workflow_run(
        thread_id="run-est-1",
        status="completed",
        run_usage=totals.model_dump(exclude={"calls"}),
    )

    run = await store.get_workflow_run("run-est-1")
    assert run is not None
    assert run.estimated_cost == 0.42  # the estimate survived
    assert run.run_usage is not None and run.run_usage["cost_usd"] > 0  # …beside the actual


@pytest.mark.asyncio
async def test_estimated_cost_absent_is_none_not_zero(tmp_path: Path) -> None:
    # An unpriceable model, or a legacy run, records no estimate — null, so the
    # UI shows no "est" rather than a US$0.00 that reads as a fact.
    store = _store(tmp_path)
    await _seed(store, "run-est-none")
    run = await store.get_workflow_run("run-est-none")
    assert run is not None
    assert run.estimated_cost is None


@pytest.mark.asyncio
async def test_estimated_cost_survives_a_later_update(tmp_path: Path) -> None:
    # The completion update writes run_usage but passes no estimate; the
    # start-time estimate must not be blanked (COALESCE on the upsert / the
    # update building its SET list from non-None args only).
    store = _store(tmp_path)
    await store.save_workflow_run(
        thread_id="run-est-keep",
        workflow_id="wf-usage",
        workflow_name="Usage Workflow",
        started_at=datetime(2026, 9, 5, 9, 0, tzinfo=timezone.utc),
        estimated_cost=0.10,
    )
    await store.update_workflow_run(thread_id="run-est-keep", execution_log="log\n")
    run = await store.get_workflow_run("run-est-keep")
    assert run is not None and run.estimated_cost == 0.10


def test_run_cost_estimate_anchors_on_first_paid_node() -> None:
    # The stored per-run estimate is priced from the run's first LLM node over
    # the resolved page count. A folder resolving to many pages must scale.
    from fichero_server.execution.runner import _estimate_run_cost
    from fichero_server.models import Workflow

    wf = Workflow(
        name="Anchored",
        description="",
        format="nodes",
        nodes=[
            {"id": "n0", "tool": "files"},  # not an LLM node — skipped
            {
                "id": "n1",
                "tool": "transcribe",
                "provider_name": "openai",
                "model_name": "gpt-4o",
            },
        ],
        edges=[],
        steps=[],
    )
    one = _estimate_run_cost(wf, resolved_count=1)
    ninety = _estimate_run_cost(wf, resolved_count=90)
    assert one is not None and ninety is not None
    # 90 pages costs ~90× one page (same per-file token assumptions).
    assert ninety == pytest.approx(one * 90, rel=1e-6)


def test_canonical_column_list_carries_run_usage() -> None:
    from fichero_server.workflows.activity_store import _WORKFLOW_RUNS_COLUMNS

    # The crash-safe rebuild copies these columns verbatim; a column missing
    # from the list is a column the rebuild silently drops.
    assert "run_usage" in _WORKFLOW_RUNS_COLUMNS
    assert "estimated_cost" in _WORKFLOW_RUNS_COLUMNS


def test_rebuild_tolerates_a_table_that_predates_the_usage_column(tmp_path: Path) -> None:
    # Recovery must not require the newest schema: a library opened before
    # the run_usage migration still has to be rebuildable, or an index
    # corruption on an old library would be unrepairable.
    import duckdb

    from fichero_server.workflows.activity_store import _rebuild_workflow_runs_flipping_stale

    db_path = str(tmp_path / "legacy.duckdb")
    conn = duckdb.connect(db_path)
    conn.execute(
        """
        CREATE TABLE workflow_runs (
            thread_id TEXT PRIMARY KEY, workflow_id TEXT, workflow_name TEXT,
            python_code TEXT, execution_log TEXT, status TEXT,
            started_at TIMESTAMP, completed_at TIMESTAMP, duration_ms FLOAT,
            error TEXT
        )
        """
    )
    conn.execute(
        "INSERT INTO workflow_runs (thread_id, workflow_id, workflow_name, status,"
        " started_at) VALUES ('zombie', 'w', 'W', 'running', CURRENT_TIMESTAMP)"
    )

    conn.close()  # the rebuild opens its own connection

    flipped = _rebuild_workflow_runs_flipping_stale(db_path, started_before=None)
    assert flipped == ["zombie"]

    check = duckdb.connect(db_path)
    status = check.execute(
        "SELECT status FROM workflow_runs WHERE thread_id = 'zombie'"
    ).fetchone()
    check.close()
    assert status is not None and status[0] == "failed"
