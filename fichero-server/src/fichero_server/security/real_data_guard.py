"""A dev engine never takes the owner's real libraries for its state (`runtime.dev-engine-refuses-real-data`, #5924).

`FICHERO_BASE_PATH` is the root of every file an engine writes (app DB, global library, caches). Pointed at
~/Fichero or ~/Fichero Projects (or anything inside) a dev or test engine would write into real data. The launchers
call this before they start; `python -m fichero_server.security.real_data_guard <path>` is the same check for a shell.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

#: Folders under the home directory that hold the owner's real libraries, and the app's real state (the default
#: state dir, which an engine with NO base path writes to).
REAL_DATA_FOLDERS = ("Fichero", "Fichero Projects", "Library/Application Support/Fichero")
#: The app containers (Debug, Dev Local, Release): ~/Library/Containers/app.fichero.*
CONTAINER_PREFIX = "app.fichero."
#: The owner's deliberate switch for running the dev engine on the real app state (start_fichero_server.sh, AGENTS.md).
#: No script sets it; a test fails if one does.
ALLOW_REAL_STATE_ENV = "FICHERO_ALLOW_REAL_STATE"


def _key(path: str | os.PathLike[str]) -> str:
    """The path with symlinks resolved and case folded (the volume is case-insensitive)."""
    return os.path.realpath(os.path.expanduser(os.fspath(path))).casefold()


def refusal(path: str | os.PathLike[str] | None, home: Path | None = None) -> str | None:
    """Why `path` may not be a dev engine's base path, in words; None when it may. NO path is refused too: the engine
    would write the default state dir, the real app's."""
    home = home or Path.home()
    if path is None or not str(path).strip():
        return ("Refusing to start: no base path is set (FICHERO_BASE_PATH), so the engine would write the real app "
                f"state in {home / 'Library/Application Support/Fichero'}. Give it a scratch folder (for example "
                "~/Fichero Dev Test/state).")
    here = _key(path)
    for folder in REAL_DATA_FOLDERS:
        root = _key(home / folder)
        if here == root or here.startswith(root + os.sep):  # a sibling such as "Fichero Dev Test" is not inside
            return (f"Refusing to start: the base path {path} is, or sits inside, {home / folder}, where the real "
                    "libraries or the app's state live. A dev engine's state goes in a scratch folder (for example "
                    "~/Fichero Dev Test/state).")
    containers = _key(home / "Library" / "Containers")
    if here.startswith(containers + os.sep):
        app = here[len(containers) + 1:].split(os.sep, 1)[0]
        if app.startswith(CONTAINER_PREFIX):
            return (f"Refusing to start: the base path {path} is inside an app container ({app}), the real app's "
                    "own state. A dev engine's state goes in a scratch folder.")
    return None


def refuse_real_base(path: str | os.PathLike[str] | None, home: Path | None = None) -> None:
    """Exit non-zero, in words, for an unset base path or one inside the real data."""
    if os.environ.get(ALLOW_REAL_STATE_ENV) == "1":  # the owner's own deliberate run (never set by a script)
        return
    said = refusal(path, home)
    if said:
        raise SystemExit(said)


if __name__ == "__main__":
    for given in sys.argv[1:] or [os.environ.get("FICHERO_BASE_PATH")]:
        refuse_real_base(given)
