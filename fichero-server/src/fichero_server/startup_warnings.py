"""What a start-up warm-up could not do, kept where a caller sees it (#4420 seam, `activity.engine.warm-up-failures-are-said`).

A warm-up (the Keychain's API keys, Vision's locales) that fails leaves the lookups to read on demand, so the engine goes
on; but a log line alone is a failure no caller can see. Each failure is kept here by name, and `GET /api/health` carries
them in its free-form `dependencies` map (`provider_keys`, `vision_locales`: `failed: <ExceptionClass>`), so the app (or a person reading health) can tell a skipped warm-up from one that never ran.
"""

from __future__ import annotations

import threading

_LOCK = threading.Lock()
_WARNINGS: dict[str, str] = {}
_PREVIOUS_STALL: str | None = None
_MULTIUSER_WORDS: str | None = None


def set_multiuser_words(text: str | None) -> None:
    """Why Multi-user started off although the environment asked for it (`multiuser.env-without-owner-password-starts-off`)."""
    global _MULTIUSER_WORDS
    with _LOCK:
        _MULTIUSER_WORDS = text


def set_previous_stall(text: str | None) -> None:
    """What held the PREVIOUS engine's event loop (`'41s in kraken_runtime:load_model'`), shown for this engine's life."""
    global _PREVIOUS_STALL
    with _LOCK:
        _PREVIOUS_STALL = text


def note(name: str, kind: str) -> None:
    """Record that warm-up `name` was skipped, and the exception CLASS name (a later note for the same name replaces it).
    Health is unauthenticated, so only the class goes out; the full text (paths, user names) is the caller's log line."""
    with _LOCK:
        _WARNINGS[name] = kind


#: The health `dependencies` key each warm-up reports under (no schema change: that map is free-form strings).
HEALTH_KEYS = {"keychain-warm-up": "provider_keys", "vision-locales-warm-up": "vision_locales"}


def as_dependencies() -> dict[str, str]:
    """The warnings as health `dependencies` entries: `{"vision_locales": "failed: OSError"}`. A warm-up that
    did not fail is absent."""
    with _LOCK:
        out = {HEALTH_KEYS.get(name, name): f"failed: {kind}" for name, kind in _WARNINGS.items()}
        if _PREVIOUS_STALL:
            out["previous_stall"] = _PREVIOUS_STALL
        if _MULTIUSER_WORDS:
            out["multiuser"] = _MULTIUSER_WORDS
        return out
