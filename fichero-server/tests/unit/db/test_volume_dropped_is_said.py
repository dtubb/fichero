"""A library on a disk that disconnects is said once, in words, as a typed 503 (`engine.silent.library-volume-dropped`, #6311).

WHY: DuckDB raised `IOException: Input/output error` for every statement and every request was its own 500 with a stack
trace (93 in one log). If this regresses the app shows a raw 500 per request and the log fills with one trace each.
"""

from __future__ import annotations

import logging

import duckdb
import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient

import fichero_server.api.main as main
from fichero_server.core import failure_ledger
from fichero_server.db import Database, volume_dropped


@pytest.fixture
def library(tmp_path):
    failure_ledger.reset()
    volume_dropped.reset()
    db = Database(tmp_path / "Archive Work.fichero" / "fichero.duckdb")
    yield db
    db.close()
    volume_dropped.reset()
    failure_ledger.reset()


def _break(db, monkeypatch):
    state = {"broken": True}
    real = db.conn

    class Conn:
        def __getattr__(self, name):
            return getattr(real, name)

        def execute(self, *args, **kwargs):
            if state["broken"]:
                raise duckdb.IOException('IO Error: Could not read from file "/Volumes/Files/x.fichero/fichero.duckdb": Input/output error')
            return real.execute(*args, **kwargs)

    monkeypatch.setattr(db, "conn", Conn())
    return state


def test_n_requests_make_one_503_one_log_line_one_ledger_entry_then_recover(library, monkeypatch, caplog):
    state = _break(library, monkeypatch)
    router = APIRouter()

    @router.get("/api/_volume_probe")
    def probe():
        return {"n": library.execute_fetchall("SELECT 1")}

    main.app.include_router(router)
    client = TestClient(main.app, raise_server_exceptions=False)
    try:
        with caplog.at_level(logging.INFO):
            responses = [client.get("/api/_volume_probe") for _ in range(7)]
        assert {r.status_code for r in responses} == {503}, [r.status_code for r in responses]
        body = responses[0].json()
        assert body["reason"] == "library_volume_not_reachable" and body["library"] == "Archive Work"
        assert "volume disconnected" in body["detail"] and "/Volumes" not in body["detail"]
        lines = [r for r in caplog.records if "volume disconnected" in r.getMessage() and r.levelno >= logging.ERROR]
        assert len(lines) == 1, [r.getMessage() for r in lines]
        counts = {k: v for k, v in failure_ledger.counts().items() if k.startswith("library-volume|")}
        assert list(counts.values()) == [7], counts

        state["broken"] = False
        assert client.get("/api/_volume_probe").status_code == 200
        assert not volume_dropped.is_down(library.path)
        state["broken"] = True
        caplog.clear()
        with caplog.at_level(logging.INFO):
            assert client.get("/api/_volume_probe").status_code == 503
        assert len([r for r in caplog.records if r.levelno >= logging.ERROR]) == 1, "a second outage is said again"
    finally:
        main.app.router.routes[:] = [r for r in main.app.router.routes if getattr(r, "path", "") != "/api/_volume_probe"]


def test_another_io_error_is_not_taken_for_a_dropped_volume(library, monkeypatch):
    class Conn:
        def __getattr__(self, name):
            return getattr(real, name)

        def execute(self, *a, **k):
            raise duckdb.IOException("IO Error: Is a directory")

    real = library.conn

    monkeypatch.setattr(library, "conn", Conn())
    with pytest.raises(duckdb.IOException) as err:
        library.execute_fetchall("SELECT 1")
    assert not isinstance(err.value, volume_dropped.LibraryVolumeNotReachable)
