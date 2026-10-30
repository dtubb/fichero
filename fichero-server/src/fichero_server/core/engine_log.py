"""engine.log stays bounded, whoever writes it (`engine.log-rotates-by-size`, `engine.logs-pruned-at-launch`).

The app captures the engine's stdout/stderr straight into engine.log, so a logging handler cannot bound it: the
engine rotates the file itself and re-points its own descriptors 1 and 2 at the fresh one. A line written between
the rename and the re-point lands in the renamed file; none is lost.
"""

from __future__ import annotations

import logging
import os
import re
import threading
import time
from collections.abc import Callable
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_MAX_BYTES = 10 * 1024 * 1024
DEFAULT_KEEP = 5
DEFAULT_MAX_AGE_DAYS = 14
_ROTATED = re.compile(r"^engine\.log\.(\d+)$")
_LOG_NAME = re.compile(r"\.log(\.\d+|\.gz)?$")


def rotate(
    log: Path,
    max_bytes: int = DEFAULT_MAX_BYTES,
    keep: int = DEFAULT_KEEP,
    after_rename: Callable[[], None] | None = None,
) -> bool:
    """Move `log` to `log.1` (shifting `.1`..`.keep-1` up, dropping `.keep`) when it is over `max_bytes`, then cut
    `log.1` to its last `max_bytes`. `after_rename` runs between the two: a live writer is re-pointed there, so the
    cut never replaces a file something is still writing to."""
    try:
        size = log.stat().st_size
    except FileNotFoundError:
        return False
    if size <= max_bytes:
        return False
    log.with_name(f"{log.name}.{keep}").unlink(missing_ok=True)
    for n in range(keep - 1, 0, -1):
        older = log.with_name(f"{log.name}.{n}")
        if older.exists():
            older.rename(log.with_name(f"{log.name}.{n + 1}"))
    first = log.with_name(f"{log.name}.1")
    log.rename(first)
    if after_rename:
        after_rename()
    _keep_tail(first, first.stat().st_size, max_bytes)
    return True


def _keep_tail(path: Path, size: int, cap: int) -> None:
    """Cut `path` to its last `cap` bytes, starting on a whole line."""
    if size <= cap:
        return
    with path.open("rb") as source:
        source.seek(size - cap)
        tail = source.read()
    newline = tail.find(b"\n")
    if newline != -1:
        tail = tail[newline + 1 :]
    scratch = path.with_name(path.name + ".tmp")
    scratch.write_bytes(tail)
    scratch.replace(path)


def _is_the_logs_folder(folder: Path) -> bool:
    """`<anything>/Logs/Fichero` as a REAL directory: neither it nor `Logs` is a symlink, and its real path is
    `Logs/Fichero` (a link into another folder, or a folder merely named Fichero elsewhere, is refused)."""
    try:
        if folder.is_symlink() or folder.parent.is_symlink() or not folder.is_dir():
            return False
        real = folder.resolve()
    except OSError:
        return False
    return real.name == "Fichero" and real.parent.name == "Logs"


def prune(
    current: Path, keep: int = DEFAULT_KEEP, max_age_days: int = DEFAULT_MAX_AGE_DAYS, now: float | None = None
) -> list[Path]:
    """Delete rotations beyond `keep` and logs older than `max_age_days` in the current log's folder.
    Never the current log, a symlink, or anything unless that folder is a real `Logs/Fichero`."""
    folder = current.parent
    if not _is_the_logs_folder(folder):
        return []
    cutoff = (time.time() if now is None else now) - max_age_days * 86400
    removed: list[Path] = []
    for root, _dirs, names in os.walk(folder, followlinks=False):
        for name in names:
            path = Path(root) / name
            if path == current or path.is_symlink() or not path.is_file():
                continue
            rotation = _ROTATED.match(name) if path.parent == folder else None
            beyond_keep = rotation is not None and int(rotation.group(1)) > keep
            too_old = _LOG_NAME.search(name) is not None and path.stat().st_mtime < cutoff
            if beyond_keep or too_old:
                path.unlink(missing_ok=True)
                removed.append(path)
    return removed


def _is_stdout(log: Path) -> bool:
    try:
        wanted, mine = log.stat(), os.fstat(1)
    except OSError:
        return False
    return (wanted.st_dev, wanted.st_ino) == (mine.st_dev, mine.st_ino)


def _repoint(log: Path) -> None:
    fd = os.open(log, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    try:
        os.dup2(fd, 1)
        os.dup2(fd, 2)
    finally:
        os.close(fd)


def _rotate_and_repoint(log: Path, max_bytes: int, keep: int) -> None:
    if _is_stdout(log):
        rotate(log, max_bytes, keep, after_rename=lambda: _repoint(log))


def start(
    log: Path,
    max_bytes: int = DEFAULT_MAX_BYTES,
    keep: int = DEFAULT_KEEP,
    interval: float = 5.0,
) -> None:
    """Rotate now and while running, and prune old logs once. Only acts when this process's stdout IS `log`
    (the app's capture); a dev engine writing to a terminal is never touched."""
    try:
        _rotate_and_repoint(log, max_bytes, keep)
        removed = prune(log, keep)
        if removed:
            logger.info("pruned %d old log file(s) from %s", len(removed), log.parent)
    except OSError:
        logger.warning("could not rotate or prune %s", log, exc_info=True)

    def watch() -> None:
        while True:
            time.sleep(interval)
            try:
                _rotate_and_repoint(log, max_bytes, keep)
            except OSError:
                logger.warning("could not rotate %s", log, exc_info=True)

    threading.Thread(target=watch, name="engine-log-rotation", daemon=True).start()
