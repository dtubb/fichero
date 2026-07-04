from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from fichero.api import main as api_main
from fichero.workflows.activity_store import ActivityStore


async def _wait_for_recovered(store: ActivityStore, thread_id: str):
    for _ in range(50):
        recovered = await store.get_workflow_run(thread_id)
        if recovered is not None and recovered.status == "failed":
            return recovered
        await asyncio.sleep(0.02)
    return await store.get_workflow_run(thread_id)


@pytest.mark.asyncio
async def test_lifespan_startup_recovers_stale_running_workflow_runs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Startup should recover zombie workflow runs in known libraries (#1350)."""
    library_path = tmp_path / "startup-recovery.fichero"
    library_path.mkdir(parents=True, exist_ok=True)
    db_path = library_path / "fichero.duckdb"

    store = ActivityStore(str(db_path))
    started_at = datetime.now(timezone.utc) - timedelta(hours=3)
    await store.save_workflow_run(
        thread_id="startup-zombie-thread",
        workflow_id="wf-startup-zombie",
        workflow_name="Startup Zombie",
        started_at=started_at,
    )

    monkeypatch.setattr(api_main, "_seed_builtin_providers", lambda: None)
    monkeypatch.setattr(api_main, "_collapse_duplicate_providers", lambda: None)
    monkeypatch.setattr(api_main, "_install_access_log_filter", lambda: None)
    monkeypatch.setattr(api_main, "_prewarm_embeddings", lambda: None)
    monkeypatch.setattr(
        api_main,
        "_discover_known_library_paths",
        lambda: [str(library_path)],
    )

    async with api_main.lifespan(api_main.app):
        recovered = await _wait_for_recovered(store, "startup-zombie-thread")

    assert recovered is not None
    assert recovered.status == "failed"


@pytest.mark.asyncio
async def test_lifespan_startup_recovers_recent_stale_running_runs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """#2223: startup must mark 'running' rows as failed even when < 2 hours old.

    The old recover_stale_runs(max_age_hours=2) default skipped recently-started
    threads to protect in-flight workflows during normal operation.  At startup
    time there are zero live workers, so that guard is wrong — any 'running' row
    is stale regardless of age.  This test verifies that a thread started just
    5 minutes ago is still marked failed after the lifespan startup sequence.
    """
    library_path = tmp_path / "recent-zombie.fichero"
    library_path.mkdir(parents=True, exist_ok=True)
    db_path = library_path / "fichero.duckdb"

    store = ActivityStore(str(db_path))
    # Started only 5 minutes ago — would survive the old max_age_hours=2 filter
    started_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    await store.save_workflow_run(
        thread_id="recent-zombie-thread",
        workflow_id="wf-recent-zombie",
        workflow_name="Recent Zombie",
        started_at=started_at,
    )

    monkeypatch.setattr(api_main, "_seed_builtin_providers", lambda: None)
    monkeypatch.setattr(api_main, "_collapse_duplicate_providers", lambda: None)
    monkeypatch.setattr(api_main, "_install_access_log_filter", lambda: None)
    monkeypatch.setattr(api_main, "_prewarm_embeddings", lambda: None)
    monkeypatch.setattr(
        api_main,
        "_discover_known_library_paths",
        lambda: [str(library_path)],
    )

    async with api_main.lifespan(api_main.app):
        recovered = await _wait_for_recovered(store, "recent-zombie-thread")

    assert recovered is not None
    assert recovered.status == "failed", (
        "#2223: a thread started 5 minutes ago must be marked 'failed' at "
        "startup — max_age_hours=0 must catch all stale runs regardless of age"
    )


@pytest.mark.asyncio
async def test_lifespan_does_not_block_on_stale_run_recovery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The API should bind before slow stale-run recovery finishes."""
    entered = False
    release_recovery = asyncio.Event()

    async def slow_recovery() -> int:
        await release_recovery.wait()
        return 0

    monkeypatch.setattr(api_main, "_seed_builtin_providers", lambda: None)
    monkeypatch.setattr(api_main, "_collapse_duplicate_providers", lambda: None)
    monkeypatch.setattr(api_main, "_install_access_log_filter", lambda: None)
    monkeypatch.setattr(api_main, "_prewarm_embeddings", lambda: None)
    monkeypatch.setattr(api_main, "_recover_stale_runs_on_startup", slow_recovery)

    async with api_main.lifespan(api_main.app):
        entered = True
        release_recovery.set()

    assert entered is True


@pytest.mark.asyncio
async def test_lifespan_shutdown_stops_managed_local_inference(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stopped = False

    async def fake_shutdown_local_inference() -> None:
        nonlocal stopped
        stopped = True

    monkeypatch.setattr(api_main, "_seed_builtin_providers", lambda: None)
    monkeypatch.setattr(api_main, "_collapse_duplicate_providers", lambda: None)
    monkeypatch.setattr(api_main, "_install_access_log_filter", lambda: None)
    monkeypatch.setattr(api_main, "_prewarm_embeddings", lambda: None)
    monkeypatch.setattr(api_main, "shutdown_managed_local_inference_services", fake_shutdown_local_inference)

    async with api_main.lifespan(api_main.app):
        pass

    assert stopped is True
