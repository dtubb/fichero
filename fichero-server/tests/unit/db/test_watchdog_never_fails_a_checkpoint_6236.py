"""The watchdog's per-tick probe never makes a CHECKPOINT fail (reviewer b22, #6236): a read of duckdb_memory() or a table
beside a writer made 184 of 300 ALTER+CHECKPOINT rounds fail on DuckDB 1.5 with "other write transactions active". The
probe is driven in a tight loop here, so a race of one tick in a few hundred shows at once."""
from __future__ import annotations

import threading

from fichero_server.db import Database, busy_evidence


def test_alter_and_checkpoint_beside_the_watchdogs_tick(tmp_path):
    db = Database(tmp_path / "wd.duckdb")
    stop = threading.Event()

    def ticks():
        alarmed: set[str] = set()
        while not stop.is_set():
            busy_evidence._tick(alarmed, set(), slow=False)

    prober = threading.Thread(target=ticks, daemon=True)
    prober.start()
    failed = []
    try:
        for i in range(300):
            try:
                db.conn.execute(f"ALTER TABLE documents ADD COLUMN IF NOT EXISTS wd_{i % 3} INTEGER")
                db.conn.execute("CHECKPOINT")
            except Exception as exc:  # noqa: BLE001 -- counted
                failed.append(str(exc))
    finally:
        stop.set()
        prober.join()
        db.close()
    assert not failed, f"{len(failed)} of 300 CHECKPOINTs failed beside the watchdog: {failed[0][:200]}"
