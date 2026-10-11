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
