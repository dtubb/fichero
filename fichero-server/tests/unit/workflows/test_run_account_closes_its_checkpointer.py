"""A status poll opened a checkpointer connection per call and never closed it (121 in a 34-minute reading run)."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

from fichero_server.workflows import checkpointer as checkpointer_module
from fichero_server.workflows import run_account


class _FakeCheckpointer:
    opened = 0
    closed = 0

    def __init__(self) -> None:
        type(self).opened += 1

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        type(self).closed += 1

    async def aget_tuple(self, _config):
        return SimpleNamespace(checkpoint={"channel_values": {"a": 1}}, pending_writes=[])


def test_fifty_polls_of_a_running_run_close_every_checkpointer_they_open(monkeypatch):
    _FakeCheckpointer.opened = _FakeCheckpointer.closed = 0
    monkeypatch.setattr(checkpointer_module.AsyncDuckDBCheckpointer, "from_db_path",
                        classmethod(lambda cls, _path, **_kw: _FakeCheckpointer()))

    async def poll():
        for _ in range(50):
            assert await run_account._checkpoint(SimpleNamespace(path="x.duckdb"), "thread") == ({"a": 1}, [])

    asyncio.run(poll())
    assert _FakeCheckpointer.opened == 50 and _FakeCheckpointer.closed == 50  # none left open


def test_the_checkpointer_is_closed_when_the_read_fails(monkeypatch):
    _FakeCheckpointer.opened = _FakeCheckpointer.closed = 0

    async def boom(self, _config):
        raise RuntimeError("unreadable")

    monkeypatch.setattr(_FakeCheckpointer, "aget_tuple", boom)
    monkeypatch.setattr(checkpointer_module.AsyncDuckDBCheckpointer, "from_db_path",
                        classmethod(lambda cls, _path, **_kw: _FakeCheckpointer()))
    try:
        asyncio.run(run_account._checkpoint(SimpleNamespace(path="x.duckdb"), "thread"))
    except RuntimeError:
        pass
    assert _FakeCheckpointer.opened == 1 and _FakeCheckpointer.closed == 1


def test_a_read_path_makes_the_checkpoint_tables_once_per_file(tmp_path):
    cls = checkpointer_module.AsyncDuckDBCheckpointer
    ran = []
    original = cls._setup
    cls._setup = lambda self: (ran.append(1), original(self))[1]
    try:
        path = tmp_path / "lib.duckdb"
        for _ in range(5):
            cls.from_db_path(path, setup_once=True).conn.close()
        assert len(ran) == 1  # five polls, one CREATE TABLE
        cls.from_db_path(path).conn.close()  # a writer still sets up as it always did
        assert len(ran) == 2
    finally:
        cls._setup = original
        checkpointer_module._TABLES_SET_UP.discard(str(path))
