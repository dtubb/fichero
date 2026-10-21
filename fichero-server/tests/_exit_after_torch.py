"""End the test process with `os._exit` once everything is closed, so torch's exit-time destructor cannot segfault (#5903).

torch 2.14's `at::native::mps::MetalShaderLibrary::~MetalShaderLibrary` crashes when libc runs the static destructors at
`exit()`: candidate 11's whole api suite passed and the process still exited 139. It happens only with libtorch loaded, so this
runs only then. The exit code is pytest's OWN (`session.exitstatus`, saved after every other `pytest_sessionfinish`), so a failing
suite still exits non-zero. Every DuckDB connection is checkpointed and closed first, so nothing is left to replay at the next
open (the WAL-replay index hazard); if that cannot be done the process exits the ordinary way instead.
"""
from __future__ import annotations

import logging
import os
import sys

import pytest

_status: int | None = None


def remember(session) -> None:
    """Save pytest's final exit status (call after the other sessionfinish hooks, which may change it)."""
    global _status
    _status = int(session.exitstatus)


def close_everything() -> None:
    """Checkpoint and close every database this process opened; raises if one is left open (the engine's own, #5929)."""
    from fichero_server.core.fast_exit import close_everything as close

    close()


def leave(config=None) -> None:
    """The hook body (pytest_unconfigure, last): leave with pytest's status when torch is loaded and all is closed."""
    if _status is None or "torch" not in sys.modules or hasattr(config, "workerinput"):
        return
    try:
        close_everything()
    except Exception as exc:  # noqa: BLE001 -- not closed: take the ordinary exit (it may crash, but never loses a write)
        print(f"fast exit skipped, a database could not be closed: {exc}", file=sys.stderr)
        return
    try:
        import atexit

        atexit._run_exitfuncs()
    except Exception:  # noqa: BLE001
        pass
    logging.shutdown()
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.flush()
        except Exception:  # noqa: BLE001 -- a closed pipe
            pass
    os._exit(_status)


class Plugin:
    """The two hooks as a registered plugin: pytest only reads a hook from a module or conftest if its name starts with
    `pytest_` (a `specname` on another name is ignored there), so an object registered with `register` is the way to
    have `remember` run last at sessionfinish and `leave` last at unconfigure."""

    @pytest.hookimpl(trylast=True)
    def pytest_sessionfinish(self, session, exitstatus):  # noqa: ARG002
        remember(session)

    @pytest.hookimpl(trylast=True)
    def pytest_unconfigure(self, config):
        leave(config)


def register(config) -> None:
    config.pluginmanager.register(Plugin(), "exit-after-torch-5903")
