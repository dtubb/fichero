"""What a start-up warm-up could not do, kept where a caller sees it (#4420 seam, `activity.engine.warm-up-failures-are-said`).

A warm-up (the Keychain's API keys, Vision's locales) that fails leaves the lookups to read on demand, so the engine goes
on; but a log line alone is a failure no caller can see. Each failure is kept here by name, and `GET /api/health` carries
them as `startup_warnings`, so the app (or a person reading health) can tell a skipped warm-up from one that never ran.
"""

from __future__ import annotations

import threading

_LOCK = threading.Lock()
_WARNINGS: dict[str, str] = {}


def note(name: str, message: str) -> None:
    """Record that warm-up `name` was skipped, and why (a later note for the same name replaces it)."""
    with _LOCK:
        _WARNINGS[name] = message


def clear(name: str) -> None:
    """A warm-up that now succeeds drops its earlier warning."""
    with _LOCK:
        _WARNINGS.pop(name, None)


def current() -> list[str]:
    """The warnings, `name: message`, in the order they were first noted."""
    with _LOCK:
        return [f"{name}: {message}" for name, message in _WARNINGS.items()]
