from __future__ import annotations

import asyncio
import builtins
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

import pytest

from fichero.api import main as api_main
from fichero.workflows.activity_store import ActivityStore


def test_library_discovery_does_not_import_typer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#3163: discovery works without the CLI dependency the bundle doesn't ship.

    Startup no longer discovers libraries at all (#3920) — but the CLI `list`
    command still calls this, and the bundle still must not drag in `typer`.
    The guard moves to the function that survived rather than dying with the
    startup caller that didn't.
    """
    library = tmp_path / "Documents" / "Recovered.fichero"
    library.mkdir(parents=True)
    monkeypatch.delitem(sys.modules, "fichero.library_discovery", raising=False)
    monkeypatch.delitem(sys.modules, "fichero.__main__", raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    real_import = builtins.__import__

    def bundled_import(name, *args, **kwargs):
        if name == "typer" or name.startswith("typer."):
            raise ModuleNotFoundError("No module named 'typer'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", bundled_import)

    from fichero.library_discovery import _discover_libraries

    assert _discover_libraries() == [str(library.resolve())]
    assert "fichero.__main__" not in sys.modules


@pytest.mark.asyncio
async def test_lifespan_never_discovers_or_opens_libraries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#3920: startup opens nothing. This is the guard against the glob returning.

    The engine used to walk ~/Documents, ~/Dropbox, ~/code and
    ~/Library/Application Support to depth 2 and open every `.fichero` it found —
    26 on the reporter's machine, almost all superseded scratch copies nobody
    asked for. `db_manager.get_database()` is get-or-CREATE, so libraries already
    open on demand; the sweep only ever pre-paid for work that may never be
    wanted.
    """
    library = tmp_path / "Documents" / "Unwanted.fichero"
    library.mkdir(parents=True)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(api_main, "_seed_builtin_providers", lambda: None)
    monkeypatch.setattr(api_main, "_collapse_duplicate_providers", lambda: None)
    monkeypatch.setattr(api_main, "_install_access_log_filter", lambda: None)

    import fichero.library_discovery as discovery

    discovered: list[str] = []
    real_discover = discovery._discover_libraries

    def spy(*args, **kwargs):
        discovered.append("called")
        return real_discover(*args, **kwargs)

    monkeypatch.setattr(discovery, "_discover_libraries", spy)

    async with api_main.lifespan(api_main.app):
        pass

    assert discovered == [], (
        "the lifespan called _discover_libraries — the startup disk glob is back "
        "(#3920). Startup must open nothing; libraries open on demand."
    )


@pytest.mark.asyncio
async def test_first_library_use_recovers_its_own_stale_runs(
    tmp_path: Path,
) -> None:
    """#1350 + #2223 survive the move off startup (#3920).

    Recovery MOVED, it did not vanish: `get_activity_tracker()` schedules
    `_recover_stale_runs_bg` the first time a library's tracker is created, so a
    zombie is cleaned when that library is first used rather than at boot for 26
    libraries nobody opened.

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
    monkeypatch.setattr(api_main, "shutdown_managed_local_inference_services", fake_shutdown_local_inference)

    async with api_main.lifespan(api_main.app):
        pass

    assert stopped is True
