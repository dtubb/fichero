"""A REAL outage: a library on a disk image that is force-detached mid-run (`engine.silent.library-volume-dropped`, #6311).

WHY: the fake-error test cannot show what DuckDB does after the disk really vanishes (the database is invalidated, the
read cursor may be served from cache, the reopen fails with another message). If this regresses a real unplug is a 500
per request again. macOS only, needs hdiutil, skipped under CI. Only the device this test attaches is ever detached.
"""

from __future__ import annotations

import logging
import os
import plistlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient

import fichero_server.api.main as main
from fichero_server.core import failure_ledger
from fichero_server.db import Database, volume_dropped

pytestmark = pytest.mark.skipif(
    sys.platform != "darwin" or shutil.which("hdiutil") is None or os.environ.get("CI"),
    reason="needs macOS and hdiutil, not under CI",
)


def _route(fn):
    def probe():
        fn()
        return {"ok": True}

    return probe


def _attach(image: Path) -> tuple[str, Path]:
    out = subprocess.run(["hdiutil", "attach", "-plist", "-nobrowse", str(image)], check=True, capture_output=True).stdout
    entities = plistlib.loads(out)["system-entities"]
    mount = next(Path(e["mount-point"]) for e in entities if e.get("mount-point"))
    device = next(e["dev-entry"] for e in entities if e.get("mount-point"))
    return device, mount


class Disk:
    def __init__(self) -> None:
        self.dir = Path(tempfile.mkdtemp(prefix="fichero6311-"))
        self.device: str | None = None
        self.mount: Path | None = None

    def start(self) -> None:
        image = self.dir / "disk.sparseimage"
        subprocess.run(["hdiutil", "create", "-size", "64m", "-type", "SPARSE", "-fs", "APFS", "-volname", "Fichero6311Test", str(image)],
                       check=True, capture_output=True)
        self.image = image
        self.device, self.mount = _attach(image)

    def _own_device(self) -> str | None:
        """The device THIS test's image is attached as, found by the image's own path: a device name is reused by macOS
        for another disk once detached, so a remembered name is never detached."""
        info = plistlib.loads(subprocess.run(["hdiutil", "info", "-plist"], capture_output=True).stdout)
        for image in info.get("images", []):
            if Path(image.get("image-path", "")).resolve() == self.image.resolve():
                return next((e["dev-entry"] for e in image["system-entities"] if e.get("mount-point")), None)
        return None

    def unplug(self) -> None:
        device = self._own_device()
        assert device, "the test image is not attached"
        subprocess.run(["hdiutil", "detach", "-force", device], check=True, capture_output=True)
        self.device = None

    def replug(self) -> None:
        self.device, self.mount = _attach(self.image)

    def cleanup(self) -> None:
        if getattr(self, "image", None) and (device := self._own_device()):
            subprocess.run(["hdiutil", "detach", "-force", device], capture_output=True)
        shutil.rmtree(self.dir, ignore_errors=True)


@pytest.fixture
def disk():
    d = Disk()
    try:
        d.start()
        yield d
    finally:
        d.cleanup()


def test_a_real_unplug_is_one_503_one_log_line_and_recovers(disk, caplog):
    failure_ledger.reset()
    volume_dropped.reset()
    path = disk.mount / "Real Unplug.fichero" / "fichero.duckdb"
    db = Database(path)
    db.execute("CREATE TABLE IF NOT EXISTS probe (n INTEGER)")
    db.execute("INSERT INTO probe VALUES (1)")
    db.checkpoint()
    probes = {
        "read": lambda: db.execute_fetchall("SELECT n FROM probe"),
        "committed_read": lambda: db.execute_fetchall("SELECT count(*) FROM probe", committed=True),
        "write": lambda: db.execute("INSERT INTO probe VALUES (2)"),
        "checkpoint": db.checkpoint,
        "commit": db.commit,
    }
    router = APIRouter()
    for name, fn in probes.items():
        router.add_api_route(f"/api/_unplug/{name}", _route(fn), methods=["GET"])
    main.app.include_router(router)
    client = TestClient(main.app, raise_server_exceptions=False)
    try:
        first = {n: client.get(f"/api/_unplug/{n}") for n in probes}
        assert all(r.status_code == 200 for r in first.values()), {n: (r.status_code, r.text[:200]) for n, r in first.items()}
        disk.unplug()
        with caplog.at_level(logging.INFO):
            codes = [(n, client.get(f"/api/_unplug/{n}").status_code) for _ in range(4) for n in probes]
        # A read DuckDB answers from its cache is real data (200); nothing may be a 500, and every write is the typed 503.
        assert {c for _, c in codes} <= {200, 503}, codes
        assert {c for n, c in codes if n == "write"} == {503}, codes
        said = [r for r in caplog.records if r.levelno >= logging.ERROR and "library" in r.getMessage().lower()
                and "reach" in r.getMessage().lower()]
        assert len(said) == 1, [r.getMessage() for r in said]
        assert volume_dropped.is_down(db.path), "a read served from cache ended the outage"
        assert not [r for r in caplog.records if "answers again" in r.getMessage()], "a cached read ended the outage"
        entries = [k for k in failure_ledger.counts() if k.startswith("library-volume|")]
        assert len(entries) == 1, entries

        disk.replug()
        path2 = disk.mount / "Real Unplug.fichero" / "fichero.duckdb"
        assert path2.exists()
        # The first statement on the old file handle may still say 503 (a checkpoint writing through a stale handle); never 500,
        # and the library carries on within a few rounds.
        for _ in range(4):
            again = {n: client.get(f"/api/_unplug/{n}").status_code for n in probes}
            assert 500 not in again.values(), again
            if set(again.values()) == {200}:
                break
        assert set(again.values()) == {200}, again
        assert not volume_dropped.is_down(db.path)
    finally:
        main.app.router.routes[:] = [r for r in main.app.router.routes if not getattr(r, "path", "").startswith("/api/_unplug/")]
        try:
            db.close()
        except Exception:  # noqa: BLE001 -- a library whose disk is gone cannot close cleanly
            pass
        volume_dropped.reset()
        failure_ledger.reset()
