"""Two threads asking for the app database at once get one instance, made once (engine start: the warm-up
thread and the lifespan both ask; two at once ran the schema setup twice and the engine failed to start with a
'Catalog write-write conflict')."""
from __future__ import annotations

import threading
import time

from fichero_server.db import app as app_db


def test_two_threads_at_once_make_one_app_database(monkeypatch):
    made = []

    class Slow:
        def __init__(self):
            made.append(self)
            time.sleep(0.2)  # the schema setup's window

    monkeypatch.setattr(app_db, "_app_db", None)
    monkeypatch.setattr(app_db, "AppDatabase", Slow)
    got = []
    threads = [threading.Thread(target=lambda: got.append(app_db.get_app_db())) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(10)
    assert len(made) == 1, f"{len(made)} app databases were made"
    assert all(g is made[0] for g in got) and len(got) == 4
