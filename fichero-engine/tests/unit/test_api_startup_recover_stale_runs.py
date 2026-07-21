from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from fichero.api import main as api_main
from fichero.workflows.activity_store import ActivityStore


# NOTE: library discovery (the home-directory `*.fichero` crawl) was removed
# entirely — the library list is the recents the app opened, never a disk sweep.
# Startup opens nothing; libraries open on demand via `db_manager.get_database()`.
# Stale-run recovery MOVED off startup onto first-library-use (below), so it no
# longer pre-pays for libraries nobody asked for.


@pytest.mark.asyncio
async def test_first_library_use_recovers_its_own_stale_runs(
    tmp_path,
) -> None:
    """#1350 + #2223 survive the move off startup (#3920).

    Recovery MOVED, it did not vanish: `get_activity_tracker()` schedules
    `_recover_stale_runs_bg` the first time a library's tracker is created, so a
    zombie is cleaned when that library is first used rather than at boot.

    `max_age_hours=0` is the #2223 half: a run that died five minutes ago is
    still stale, because the tracker is created once per library per process, so
    nothing in this process can be in flight yet.
    """
    from fichero.workflows.activity import get_activity_tracker

    library_path = tmp_path / "lazy-zombie.fichero"
    library_path.mkdir(parents=True, exist_ok=True)
    db_path = library_path / "fichero.duckdb"

    store = ActivityStore(str(db_path))
    await store.save_workflow_run(
        thread_id="lazy-zombie-thread",
        workflow_id="wf-lazy-zombie",
        workflow_name="Lazy Zombie",
        # only 5 minutes old — the default max_age_hours=2 would skip this (#2223)
        started_at=datetime.now(timezone.utc) - timedelta(minutes=5),
    )

    # First use of this library — this is what schedules recovery.
    get_activity_tracker(str(db_path))

    recovered = await _wait_for_recovered(store, "lazy-zombie-thread")
    assert recovered is not None
    assert recovered.status == "failed", (
        "first use of a library must recover its stale runs (#1350), including "
        "ones started minutes ago (#2223 — max_age_hours=0)"
    )


async def _wait_for_recovered(store: ActivityStore, thread_id: str):
    for _ in range(50):
        recovered = await store.get_workflow_run(thread_id)
        if recovered is not None and recovered.status == "failed":
            return recovered
        await asyncio.sleep(0.02)
    return await store.get_workflow_run(thread_id)


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
    monkeypatch.setattr(
        api_main,
        "shutdown_managed_local_inference_services",
        fake_shutdown_local_inference,
    )

    async with api_main.lifespan(api_main.app):
        pass

    assert stopped is True
