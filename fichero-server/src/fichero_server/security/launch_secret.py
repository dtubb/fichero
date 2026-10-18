"""The per-launch secret that authorises first-run (multiuser-always-on, "Transports and the two secrets").

The app makes 32 random bytes at each launch and hands them to the engine it spawns over an inherited pipe (never
an environment variable, argv or a file; Debug Dev Local alone adds a 0600 file). The engine keeps them in memory
only. Slice 4 adds the route that checks it; the pipe read at engine start-up and the migrate-owner and reset routes
follow in later slices.
"""

from __future__ import annotations

import hmac
import os
import re
import stat
from collections.abc import Mapping
from typing import TextIO

_HEX_32_BYTES = re.compile(r"[0-9a-f]{64}")
_secret: str | None = None


def set_secret(secret: str | None) -> None:
    global _secret
    _secret = secret or None


def matches(candidate: str | None) -> bool:
    """Constant-time; an engine with no secret, or a missing candidate, never matches."""
    if not _secret or not candidate:
        return False
    return hmac.compare_digest(_secret.encode(), candidate.encode())


def _set_checked(text: str) -> None:
    candidate = text.strip().lower()
    if not _HEX_32_BYTES.fullmatch(candidate):
        raise ValueError("the launch secret is 32 random bytes as 64 hex characters")
    set_secret(candidate)


def read_from_stream(stream: TextIO) -> None:
    """Take the secret from one line of the stream (the pipe the app spawned us with)."""
    _set_checked(stream.readline())


def read_from_file(path: str) -> None:
    """Debug Dev Local only: the dev script's 0600 file. Refused unless ours and closed to group and others.

    The app deletes the file after reading it; the engine leaves it alone."""
    info = os.stat(path)
    if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
        raise ValueError("the launch-secret file must be owned by this user and mode 0600")
    with open(path, encoding="ascii") as handle:
        _set_checked(handle.read())


def load_at_startup(environ: Mapping[str, str], stdin: TextIO) -> None:
    """The one place an engine takes the secret. A flag (not the secret) says the app spawned us over a pipe.

    A `--reload` dev engine cannot inherit stdin, so it names the dev file instead. With neither, first-run stays closed."""
    if environ.get("FICHERO_LAUNCH_SECRET_STDIN") == "1":
        read_from_stream(stdin)
    elif environ.get("FICHERO_DEV_LAUNCH_SECRET_FILE"):
        read_from_file(environ["FICHERO_DEV_LAUNCH_SECRET_FILE"])
