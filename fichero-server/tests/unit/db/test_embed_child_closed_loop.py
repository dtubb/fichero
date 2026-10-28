"""The embedding child stops lancedb's loop thread, and a loop already closed is nothing to stop (review 2026-10-27).

WHY: `call_soon_threadsafe` on a closed loop raises RuntimeError, which ended the child before it loaded its model.
"""

from __future__ import annotations

import asyncio
import sys
from types import ModuleType, SimpleNamespace

from fichero_server.db import embed_process


def test_a_closed_lancedb_loop_is_left_alone(monkeypatch):
    loop = asyncio.new_event_loop()
    loop.close()
    joined: list[float] = []
    background = ModuleType("lancedb.background_loop")
    background.LOOP = SimpleNamespace(loop=loop, thread=SimpleNamespace(join=joined.append))
    monkeypatch.setitem(sys.modules, "lancedb.background_loop", background)

    embed_process._stop_lancedbs_loop()  # no RuntimeError

    assert joined == []
