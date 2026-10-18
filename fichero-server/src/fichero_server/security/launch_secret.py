"""The per-launch secret that authorises first-run (multiuser-always-on, "Transports and the two secrets").

The app makes 32 random bytes at each launch and hands them to the engine it spawns over an inherited pipe (never
an environment variable, argv or a file; Debug Dev Local alone adds a 0600 file). The engine keeps them in memory
only. Slice 4 adds the route that checks it; the pipe read at engine start-up and the migrate-owner and reset routes
follow in later slices.
"""

from __future__ import annotations

import hmac
import logging
import os
import re
import stat
from collections.abc import Mapping
from typing import TextIO

logger = logging.getLogger(__name__)
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
    # O_NOFOLLOW + fstat on the opened fd: a symlink swap between check and read cannot redirect us.
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, encoding="ascii") as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
            raise ValueError("the launch-secret file must be a regular file owned by this user and mode 0600")
        _set_checked(handle.read())


def _ready(stream: TextIO, timeout: float) -> bool:
    """Whether a line can be read within `timeout`; an in-memory stream (tests) always can."""
    import select

    try:
        fd = stream.fileno()
    except (AttributeError, OSError, ValueError):
        return True
    return bool(select.select([fd], [], [], timeout)[0])


def _is_pipe_or_memory(stream: TextIO) -> bool:
    """True for a pipe (what the app hands us) or an in-memory stream (tests); a tty, file or /dev/null is not."""
    try:
        return stat.S_ISFIFO(os.fstat(stream.fileno()).st_mode)
    except (AttributeError, OSError, ValueError):
        return True


def load_at_startup(environ: Mapping[str, str], stdin: TextIO, *, timeout: float = 5.0) -> None:
    """The one place an engine takes the secret. A flag (not the secret) says the app spawned us over a pipe.

    A `--reload` dev engine cannot inherit stdin, so it names the dev file instead (honoured only when FICHERO_ENV=development, which the dev script sets). With neither, first-run stays closed.

    Waits at all only when the flag is set AND stdin is a pipe; the app always writes one line (the secret, or empty)
    and closes it, so the read returns at once and `timeout` is only a backstop. Never raises: a secret that does not arrive, arrives malformed, or a file that
    cannot be read leaves first-run closed and the engine starts (#5797: nothing may stop the embedded app's launch)."""
    try:
        if environ.get("FICHERO_LAUNCH_SECRET_STDIN") == "1":
            if not _is_pipe_or_memory(stdin):
                raise ValueError("the launch-secret flag is set but stdin is not a pipe")
            if not _ready(stdin, timeout):
                raise ValueError(f"no launch secret on stdin within {timeout:g} s")
            read_from_stream(stdin)
        elif environ.get("FICHERO_DEV_LAUNCH_SECRET_FILE") and environ.get("FICHERO_ENV") == "development":
            read_from_file(environ["FICHERO_DEV_LAUNCH_SECRET_FILE"])
    except (ValueError, OSError) as exc:
        logger.warning("Launch secret not taken (%s); first-run stays closed", exc)
