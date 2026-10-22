"""`get_app_db` builds the app database once, even when two threads ask on a cold process (#6007): the lifespan test failed one run in four
with a DuckDB write-write conflict on `providers`, two AppDatabase objects running their schema setup on the same file."""
from __future__ import annotations

import threading
import time

from fichero_server.db import app as app_db_module


def test_two_threads_asking_on_a_cold_process_get_the_same_object(monkeypatch):
    made = []

    class Slow:
        def __init__(self):
            made.append(self)
            time.sleep(0.2)  # the schema setup: long enough for the other thread to arrive

    monkeypatch.setattr(app_db_module, "_app_db", None)
    monkeypatch.setattr(app_db_module, "AppDatabase", Slow)
    got = []
    threads = [threading.Thread(target=lambda: got.append(app_db_module.get_app_db())) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(10)
    assert len(made) == 1, f"{len(made)} app databases were built"
    assert len({id(x) for x in got}) == 1 and len(got) == 4
