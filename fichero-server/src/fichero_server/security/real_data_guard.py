"""A dev engine never takes the owner's real libraries for its state (`runtime.dev-engine-refuses-real-data`, #5898 lane).

`FICHERO_BASE_PATH` is the root of every file an engine writes (app DB, global library, caches). Pointed at
~/Fichero or ~/Fichero Projects (or anything inside) a dev or test engine would write into real data. The launchers
call this before they start; `python -m fichero_server.security.real_data_guard <path>` is the same check for a shell.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

#: Folders under the home directory that hold the owner's real libraries.
REAL_DATA_FOLDERS = ("Fichero", "Fichero Projects")


def _key(path: str | os.PathLike[str]) -> str:
    """The path with symlinks resolved and case folded (the volume is case-insensitive)."""
    return os.path.realpath(os.path.expanduser(os.fspath(path))).casefold()


def refusal(path: str | os.PathLike[str] | None, home: Path | None = None) -> str | None:
    """Why `path` may not be a dev engine's base path, in words; None when it may (or none was given)."""
    if path is None or not str(path).strip():
        return None
    home = home or Path.home()
    here = _key(path)
    for folder in REAL_DATA_FOLDERS:
        root = _key(home / folder)
        if here == root or here.startswith(root + os.sep):  # a sibling such as "Fichero Dev Test" is not inside
            return (f"Refusing to start: the base path {path} is, or sits inside, {home / folder}, where the real "
                    "libraries live. A dev engine's state goes in a scratch folder (for example ~/Fichero Dev Test/state).")
    return None


def refuse_real_base(path: str | os.PathLike[str] | None, home: Path | None = None) -> None:
    """Exit non-zero, in words, for a base path inside the real data."""
    said = refusal(path, home)
    if said:
        raise SystemExit(said)


if __name__ == "__main__":
    for given in sys.argv[1:] or [os.environ.get("FICHERO_BASE_PATH")]:
        refuse_real_base(given)
