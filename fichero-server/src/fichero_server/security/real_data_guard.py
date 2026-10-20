"""A dev engine never takes the owner's real libraries for its state (`runtime.dev-engine-refuses-real-data`, #5924).

`FICHERO_BASE_PATH` is the root of every file an engine writes (app DB, global library, caches). Pointed at
~/Fichero or ~/Fichero Projects (or anything inside) a dev or test engine would write into real data. The launchers
call this before they start; `python -m fichero_server.security.real_data_guard <path>` is the same check for a shell.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

#: Always refused, switch or not: the owner's real libraries.
REAL_LIBRARY_FOLDERS = ("Fichero", "Fichero Projects")
#: The app's real state: what an engine with NO base path writes (the default state dir). Only the owner's switch lifts these.
APP_STATE_FOLDERS = ("Library/Application Support/Fichero",)
#: Always refused: the app containers, ~/Library/Containers/app.fichero.*, and the legacy ~/Library/Application Support/app.fichero.*
APP_ID_PREFIX = "app.fichero."
#: The owner's deliberate switch for running the dev engine on the real app STATE (start_fichero_server.sh, AGENTS.md):
#: it lifts the unset-base and default-state refusals ONLY, never the libraries or the containers. No script sets it;
#: a test fails if one does.
ALLOW_REAL_STATE_ENV = "FICHERO_ALLOW_REAL_STATE"


def _key(path: str | os.PathLike[str]) -> str:
    """The path with symlinks resolved and case folded (the volume is case-insensitive)."""
    return os.path.realpath(os.path.expanduser(os.fspath(path))).casefold()


def _inside(here: str, root: str) -> bool:
    return here == root or here.startswith(root + os.sep)  # a sibling such as "Fichero Dev Test" is not inside


def refusal(path: str | os.PathLike[str] | None, home: Path | None = None, *, allow_state: bool = False) -> str | None:
    """Why `path` may not be a dev engine's base path, in words; None when it may. NO path is refused too: the engine
    would write the default state dir, the real app's. `allow_state` (the owner's switch) lifts only that and the
    default state dir, never the libraries or the app containers."""
    home = home or Path.home()
    state = home / APP_STATE_FOLDERS[0]
    if path is None or not str(path).strip():
        if allow_state:
            return None
        return ("Refusing to start: no base path is set (FICHERO_BASE_PATH), so the engine would write the real app "
                f"state in {state}. Give it a scratch folder (for example ~/Fichero Dev Test/state).")
    here = _key(path)
    for folder in REAL_LIBRARY_FOLDERS:
        if _inside(here, _key(home / folder)):
            return (f"Refusing to start: the base path {path} is, or sits inside, {home / folder}, where the real "
                    "libraries live. A dev engine's state goes in a scratch folder (for example ~/Fichero Dev Test/state).")
    for parent in (home / "Library" / "Containers", home / "Library" / "Application Support"):
        root = _key(parent)
        if here.startswith(root + os.sep):
            app = here[len(root) + 1:].split(os.sep, 1)[0]
            if app.startswith(APP_ID_PREFIX):
                return (f"Refusing to start: the base path {path} is inside the app's own folder {parent / app}. "
                        "A dev engine's state goes in a scratch folder.")
    if not allow_state and _inside(here, _key(state)):
        return (f"Refusing to start: the base path {path} is, or sits inside, {state}, the real app's state. "
                "A dev engine's state goes in a scratch folder (for example ~/Fichero Dev Test/state).")
    return None


def refuse_real_base(path: str | os.PathLike[str] | None, home: Path | None = None) -> None:
    """Exit non-zero, in words, for an unset base path or one inside the real data."""
    said = refusal(path, home, allow_state=os.environ.get(ALLOW_REAL_STATE_ENV) == "1")  # the owner's, by hand
    if said:
        raise SystemExit(said)


if __name__ == "__main__":
    for given in sys.argv[1:] or [os.environ.get("FICHERO_BASE_PATH")]:
        refuse_real_base(given)
