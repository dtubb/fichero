from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from fichero.api import main as api_main
from fichero.workflows.activity_store import ActivityStore


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
        pass

    recovered = await store.get_workflow_run("startup-zombie-thread")
    assert recovered is not None
    assert recovered.status == "failed"
