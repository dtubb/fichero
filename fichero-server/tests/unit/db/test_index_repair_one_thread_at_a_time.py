"""Two threads opening the same project never rebuild its indexes at once (M4 suite 2026-10-11).

Two embedding workers each ran `Database.__init__` → `_repair_indexes_once` on one project together;
both dropped and re-created the secondary indexes, and DuckDB crashed the process (segmentation fault).
"""
import threading
import time

import fichero_server.db as db_module


def test_the_repair_runs_one_thread_at_a_time_per_project():
    inside, most = [0], [0]
    guard = threading.Lock()

    def locked_body(self):
        with guard:
            inside[0] += 1
            most[0] = max(most[0], inside[0])
        time.sleep(0.05)
        with guard:
            inside[0] -= 1

    class Fake:
        path = "/projects/one.fichero"
        _repair_indexes_once_locked = locked_body

    threads = [threading.Thread(target=db_module.Database._repair_indexes_once, args=(Fake(),)) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert most[0] == 1


def test_two_projects_repair_side_by_side():
    assert db_module._repair_lock("/a.fichero") is db_module._repair_lock("/a.fichero")
    assert db_module._repair_lock("/a.fichero") is not db_module._repair_lock("/b.fichero")


def test_a_new_library_is_not_rebuilt_on_every_open(tmp_path, monkeypatch):
    """A library with no settings table has nothing written before the #5644 fix: no rebuild, ever."""
    calls = []
    monkeypatch.setattr(db_module, "rebuild_secondary_indexes", lambda conn: calls.append(1) or (0, 0))

    class Conn:
        def execute(self, *_):
            class R:
                def fetchone(self):
                    return None

                def fetchall(self):  # results are read to the end (#6236, `fetch_one`)
                    return []
            return R()

    class Fake:
        path = str(tmp_path / "new.fichero")
        conn = Conn()
        INDEXES_REPAIRED_SETTING = db_module.Database.INDEXES_REPAIRED_SETTING
        _repair_indexes_once_locked = db_module.Database._repair_indexes_once_locked

    for _ in range(3):
        db_module.Database._repair_indexes_once(Fake())
    assert calls == []
