"""A restore stops every open job first and says how many (`safety.net.restore-stops-the-workers-first`, #5246)."""
from __future__ import annotations

from fichero_server.execution import jobs


def test_stop_everything_cancels_waiting_and_paused_jobs_and_counts_them(db, monkeypatch):
    monkeypatch.setattr(jobs._scheduler, "wake", lambda key: None)
    jobs.register_kind("test-restore-stop", lambda _db, _subject: None, model=None, lane="database", name="Test")
    a = jobs.enqueue(db, "test-restore-stop", "p1")
    b = jobs.enqueue(db, "test-restore-stop", "p2")
    jobs.pause_job(db, b, True)
    assert jobs.stop_everything(db) == 2
    assert all(db.execute_fetchone("SELECT state FROM jobs WHERE id = ?", [i])[0] == "cancelled" for i in (a, b))


def test_nothing_open_stops_nothing(db):
    assert jobs.stop_everything(db) == 0


def test_the_restore_route_stops_the_open_jobs_first(monkeypatch):
    from fichero_server.api.routes.system import storage

    calls: list[str] = []
    monkeypatch.setattr(storage, "_stop_the_workers", lambda path: calls.append("stop") or 3)
    monkeypatch.setattr(storage, "restore_snapshot", lambda sid: calls.append("restore") or {
        "snapshot_id": sid, "library_path": "/x", "duckdb_restored_path": None, "lance_restored_path": None, "note": "ok"})
    snap = type("S", (), {"id": "s1", "library_path": "/x", "initiator": type("I", (), {"value": "user"})()})()
    monkeypatch.setattr(storage, "list_snapshots", lambda include_expired=True: [snap])
    monkeypatch.setattr(storage, "_record_snapshot_audit", lambda **kw: None)
    monkeypatch.setattr(storage, "_emit_snapshot_change", lambda *a, **kw: None)
    import asyncio

    out = asyncio.run(storage.restore_library_snapshot("s1"))
    assert calls == ["stop", "restore"]
    assert out.note.startswith("3 job(s) stopped first")
