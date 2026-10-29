"""`Database.lance` returns the connection it made (#6122): another thread on the same Database may reset `_lance_db`
(the folder's embedding choice changed under it) between the connect and the return. It re-read the attribute and handed
its caller None (seen in a mixed run: "'NoneType' object has no attribute 'open_table'")."""
from __future__ import annotations

import contextlib

from fichero_server.db import Database, vector_swap


def test_a_reset_by_another_thread_after_the_connect_does_not_hand_the_caller_none(tmp_path, monkeypatch):
    db = Database(tmp_path / "lib" / "library.duckdb")
    try:
        real_lock = vector_swap.package_lock

        @contextlib.contextmanager
        def another_thread_resets_on_the_way_out(package):
            with real_lock(package):
                yield
            db._lance_db = None  # what a second thread's stamp check does, in this window

        monkeypatch.setattr(vector_swap, "package_lock", another_thread_resets_on_the_way_out)
        assert db.lance is not None
    finally:
        db.close()
