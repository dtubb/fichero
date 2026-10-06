"""No test opens a database in, or writes into, the maintainer's real Fichero state (#5530).

That is ~/Library/Application Support/Fichero (and its legacy siblings) and the sandboxed app's
containers under ~/Library/Containers.

WHY: a gate run errored 12 times because the dev engine held the lock on
``~/Library/Application Support/Fichero/global.fichero`` -- a test fixture was opening the
maintainer's REAL global library (his project registry, owner grants, default workflows), and
could have written test rows into it. The conftest points ``FICHERO_BASE_PATH`` at a temp dir and
every engine-owned path derives from that, but one module reload (or one hard-coded path) is enough
to slip out. This turns "tests never touch the real state" into a check that names the test.

Two seams, both runtime (a source scan cannot follow a path built three calls away):

* ``duckdb.connect`` is wrapped: opening ANY DuckDB file under a real state dir is refused, even
  read-only (a read-only open still fights the running engine for the lock).
* an audit hook refuses writes there: ``open`` for writing, ``os.mkdir``, ``os.rename`` /
  ``os.replace``, ``os.remove`` / ``os.unlink``, ``os.rmdir``, ``os.symlink``, ``shutil.rmtree``,
  and a Unix ``socket.bind`` (the sandboxed app's engine socket is in its container).

The refusal raises AssertionError at the call, so nothing is touched, AND is recorded, so a caller
that swallows the error still fails its test at teardown (``drain``). Reads of files are not
judged: the model stores live under the test base too, so a read of the real store only happens
through ``share_real_embedding_cache``, the one explicit opt-in (and a write through it is refused).

The real home is taken from the password database at import, before any test can monkeypatch
``HOME`` or ``Path.home``.
"""

from __future__ import annotations

import os
import pwd
import sys
import threading
from pathlib import Path

#: The real home, read before any test could change HOME.
REAL_HOME = os.path.realpath(pwd.getpwuid(os.getuid()).pw_dir)
_SUPPORT = os.path.join(REAL_HOME, "Library", "Application Support")
_CONTAINERS = os.path.join(REAL_HOME, "Library", "Containers")
#: Every dir an engine or app build of Fichero keeps state in: the canonical one and the legacy
#: ones `migrate_legacy_server_state` moves from, and the sandboxed app's containers -- the running
#: app's engine socket lives at app.fichero.fichero/Data/tmp/fichero.sock, and on 2026-10-06 it was
#: unlinked under a live engine.
ROOTS: tuple[str, ...] = tuple(
    os.path.join(_SUPPORT, name)
    for name in ("Fichero", "com.fichero.fichero", "ca.tubb.fichero", "app.fichero.fichero")
) + tuple(
    os.path.join(_CONTAINERS, name) for name in ("app.fichero.fichero", "app.fichero.fichero.fichero_server")
)

_violations: list[str] = []
_busy = threading.local()
_installed = False

_WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND


def real_state_root(path) -> str | None:
    """The real state root ``path`` falls under (after resolving links), or None."""
    if isinstance(path, int) or path is None:
        return None
    try:
        text = os.fsdecode(os.fspath(path))
    except TypeError:
        return None
    if not text or text == ":memory:" or text.startswith(":memory:"):
        return None
    candidates = {os.path.abspath(text), os.path.realpath(text)}
    for root in ROOTS:
        for candidate in candidates:
            if candidate == root or candidate.startswith(root + os.sep):
                return root
    return None


def _current_test() -> str:
    return os.environ.get("PYTEST_CURRENT_TEST", "<no test running>").rsplit(" (", 1)[0]


def _refuse(action: str, path) -> None:
    message = (
        f"{_current_test()}: {action} {os.fsdecode(os.fspath(path))} -- that is the maintainer's "
        "real Fichero state (#5530). Point it at tmp_path / the test base "
        "(settings.base_path, server_state_dir()) instead."
    )
    _violations.append(message)
    raise AssertionError(message)


def check(action: str, path) -> None:
    """Refuse ``action`` on ``path`` when it falls under a real state root."""
    if getattr(_busy, "on", False):
        return
    _busy.on = True
    try:
        hit = real_state_root(path) is not None
    finally:
        _busy.on = False
    if hit:
        _refuse(action, path)


def _is_write_open(mode, flags) -> bool:
    if isinstance(mode, str):
        return any(c in mode for c in "wax+")
    if isinstance(flags, int):
        return bool(flags & _WRITE_FLAGS)
    return False


def _audit(event: str, args: tuple) -> None:
    if event == "open":
        path = args[0]
        mode = args[1] if len(args) > 1 else None
        flags = args[2] if len(args) > 2 else None
        if _is_write_open(mode, flags):
            check("writes", path)
    elif event == "os.mkdir":
        # Path.mkdir(exist_ok=True) on an existing dir writes nothing.
        if not os.path.lexists(args[0]):
            check("makes a directory at", args[0])
    elif event == "os.rename":
        check("moves", args[0])
        check("moves onto", args[1])
    elif event in ("os.remove", "os.rmdir", "shutil.rmtree"):
        check("removes", args[0])
    elif event == "os.symlink":
        check("makes a link at", args[1])
    elif event == "socket.bind":
        # A Unix socket bound there would take the running app's engine socket path.
        address = args[1] if len(args) > 1 else None
        if isinstance(address, (str, bytes)):
            check("binds a socket at", address)


def _wrap_duckdb() -> None:
    import duckdb

    real_connect = duckdb.connect
    if getattr(real_connect, "_fichero_real_state_guard", False):
        return

    def connect(database=":memory:", *args, **kwargs):
        check("opens the DuckDB file", database)
        return real_connect(database, *args, **kwargs)

    connect._fichero_real_state_guard = True  # type: ignore[attr-defined]
    connect.__wrapped__ = real_connect  # type: ignore[attr-defined]
    duckdb.connect = connect


def install() -> None:
    """Arm both seams once per process."""
    global _installed
    if _installed:
        return
    _installed = True
    _wrap_duckdb()
    sys.addaudithook(_audit)


def drain() -> list[str]:
    """Every refusal since the last drain (and forget them)."""
    out = list(_violations)
    _violations.clear()
    return out


def share_real_embedding_cache(test_models_dir: Path) -> Path | None:
    """The one read of the real model store tests are allowed: the pinned embedding model.

    Link ``<test base>/models/embeddings`` to the real ``models/embeddings`` so tests that embed use
    the model this Mac already has (HF_HUB_OFFLINE keeps it from downloading) instead of failing;
    every other store (spaCy, Whisper, MLX, Kraken) stays an empty temp dir. A write that resolves
    through the link is still refused by the guard. Returns the link, or None when this Mac has no
    embedding cache (the tests that need it then fail or skip as on a clean machine, #5528).
    """
    real = Path(ROOTS[0]) / "models" / "embeddings"
    if not real.is_dir():
        return None
    test_models_dir.mkdir(parents=True, exist_ok=True)
    link = test_models_dir / "embeddings"
    if not link.exists() and not link.is_symlink():
        link.symlink_to(real, target_is_directory=True)
    return link
