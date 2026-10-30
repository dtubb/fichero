"""`engine.log-rotates-by-size`, `engine.logs-pruned-at-launch` (owner 2026-10-30).

WHY: the app captures the engine's stdout/stderr into engine.log, so the engine's own RotatingFileHandler never
bounded it: 166 MB on one machine. If these regress, the file grows without bound again, or pruning deletes
something that is not an old log of Fichero's.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
import time
from pathlib import Path

from fichero_server.core import engine_log

DAY = 86400


def _logs(tmp_path: Path) -> Path:
    folder = tmp_path / "Logs" / "Fichero"
    folder.mkdir(parents=True)
    return folder


def test_a_log_under_the_cap_is_left_alone(tmp_path):
    log = _logs(tmp_path) / "engine.log"
    log.write_text("small\n")
    assert engine_log.rotate(log, max_bytes=100, keep=5) is False
    assert log.read_text() == "small\n"


def test_an_over_cap_log_rotates_and_only_the_last_five_are_kept(tmp_path):
    folder = _logs(tmp_path)
    log = folder / "engine.log"
    for generation in range(8):
        log.write_text(f"gen{generation}\n" * 40)
        assert engine_log.rotate(log, max_bytes=100, keep=5) is True
    names = sorted(p.name for p in folder.iterdir())
    assert names == ["engine.log.1", "engine.log.2", "engine.log.3", "engine.log.4", "engine.log.5"]
    assert (folder / "engine.log.1").read_text().startswith("gen7")
    assert (folder / "engine.log.5").read_text().startswith("gen3")


def test_a_huge_existing_log_is_kept_as_its_last_cap_bytes_on_whole_lines(tmp_path):
    folder = _logs(tmp_path)
    log = folder / "engine.log"
    log.write_text("".join(f"line {n:05d}\n" for n in range(1000)))      # 11,000 bytes
    engine_log.rotate(log, max_bytes=1000, keep=5)
    kept = (folder / "engine.log.1").read_bytes()
    assert len(kept) <= 1000
    assert kept.startswith(b"line ") and kept.endswith(b"line 00999\n")
    assert not log.exists()


def test_prune_removes_old_logs_and_extra_rotations_and_never_the_current_log(tmp_path):
    folder = _logs(tmp_path)
    now = time.time()
    current = folder / "engine.log"
    current.write_text("now")
    os.utime(current, (now - 30 * DAY, now - 30 * DAY))           # quiet for a month: still never deleted
    fresh = folder / "engine.log.1"
    fresh.write_text("x")
    stale = folder / "engine.log.2"
    stale.write_text("x")
    os.utime(stale, (now - 15 * DAY, now - 15 * DAY))
    beyond = folder / "engine.log.9"
    beyond.write_text("x")                                        # a rotation beyond the 5 kept
    old_app = folder / "app.log"
    old_app.write_text("x")
    os.utime(old_app, (now - 20 * DAY, now - 20 * DAY))
    other = folder / "notes.txt"
    other.write_text("not a log")
    os.utime(other, (now - 90 * DAY, now - 90 * DAY))
    (folder / "crash").mkdir()
    old_crash = folder / "crash" / "a.log"
    old_crash.write_text("x")
    os.utime(old_crash, (now - 20 * DAY, now - 20 * DAY))

    removed = engine_log.prune(current, keep=5, max_age_days=14, now=now)

    assert sorted(p.name for p in removed) == ["a.log", "app.log", "engine.log.2", "engine.log.9"]
    assert current.exists() and fresh.exists() and other.exists()
    assert (folder / "crash").is_dir()


def test_prune_touches_nothing_outside_a_folder_named_fichero(tmp_path):
    folder = tmp_path / "Documents"
    folder.mkdir()
    log = folder / "engine.log"
    log.write_text("x")
    victim = folder / "old.log"
    victim.write_text("x")
    old = time.time() - 40 * DAY
    os.utime(victim, (old, old))
    assert engine_log.prune(log, keep=5, max_age_days=14) == []
    assert victim.exists()


def test_prune_never_follows_a_symlink_out_of_the_folder(tmp_path):
    folder = _logs(tmp_path)
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    precious = outside / "precious.log"
    precious.write_text("keep me")
    old = time.time() - 40 * DAY
    os.utime(precious, (old, old))
    (folder / "link").symlink_to(outside)
    (folder / "file.log").symlink_to(precious)
    current = folder / "engine.log"
    current.write_text("x")
    engine_log.prune(current, keep=5, max_age_days=14)
    assert precious.read_text() == "keep me"


def test_a_running_engine_is_rotated_while_it_writes_through_the_raw_stream(tmp_path):
    """The real mechanism, in a child process: fds 1 and 2 are re-pointed at a fresh engine.log, so the file is
    bounded though the writer is plain print() and C-level stderr, as under the app's capture."""
    folder = _logs(tmp_path)
    log = folder / "engine.log"
    script = textwrap.dedent(
        f"""
        import os, sys, time
        from pathlib import Path
        from fichero_server.core import engine_log
        engine_log.start(Path({str(log)!r}), max_bytes=2000, keep=3, interval=0.01)
        for n in range(400):
            print(f"stdout line {{n:04d}} " + "x" * 40, flush=True)
            os.write(2, f"stderr line {{n:04d}}\\n".encode())
            time.sleep(0.002)
        time.sleep(0.3)
        print("LAST", flush=True)
        """
    )
    with log.open("wb"):
        pass
    with log.open("ab") as capture:
        subprocess.run([sys.executable, "-c", script], stdout=capture, stderr=capture, check=True, timeout=60)
    files = sorted(p.name for p in folder.iterdir())
    assert "engine.log.1" in files and len(files) <= 4, files
    assert "LAST" in log.read_text()
    assert all(p.stat().st_size < 2000 + 2000 for p in folder.iterdir()), [(p.name, p.stat().st_size) for p in folder.iterdir()]


def test_prune_refuses_a_log_folder_that_is_a_symlink(tmp_path):
    real = tmp_path / "elsewhere"
    real.mkdir()
    precious = real / "precious.log"
    precious.write_text("x")
    old = time.time() - 40 * DAY
    os.utime(precious, (old, old))
    (tmp_path / "Logs").mkdir()
    (tmp_path / "Logs" / "Fichero").symlink_to(real)
    current = tmp_path / "Logs" / "Fichero" / "engine.log"
    current.write_text("x")
    assert engine_log.prune(current, keep=5, max_age_days=14) == []
    assert precious.exists()


def test_prune_requires_the_folder_to_be_logs_slash_fichero(tmp_path):
    folder = tmp_path / "Documents" / "Fichero"          # named Fichero, but not under a Logs folder
    folder.mkdir(parents=True)
    victim = folder / "old.log"
    victim.write_text("x")
    old = time.time() - 40 * DAY
    os.utime(victim, (old, old))
    current = folder / "engine.log"
    current.write_text("x")
    assert engine_log.prune(current, keep=5, max_age_days=14) == []
    assert victim.exists()
