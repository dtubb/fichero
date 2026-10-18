"""The per-launch secret that authorises first-run (multiuser-always-on, "Transports and the two secrets").

The app makes 32 random bytes at each launch and hands them to the engine it spawns over an inherited pipe (never
an environment variable, argv or a file; Debug Dev Local alone adds a 0600 file). The engine keeps them in memory
only. Slice 4 adds the route that checks it; the pipe read at engine start-up and the migrate-owner and reset routes
follow in later slices.
"""

from __future__ import annotations

import hmac

_secret: str | None = None


def set_secret(secret: str | None) -> None:
    global _secret
    _secret = secret or None


def matches(candidate: str | None) -> bool:
    """Constant-time; an engine with no secret, or a missing candidate, never matches."""
    if not _secret or not candidate:
        return False
    return hmac.compare_digest(_secret.encode(), candidate.encode())
