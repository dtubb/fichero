"""Swapping a project's whole vector folder for a rebuilt one, so that a crash at any step leaves it whole (#6122, review ## 1284).

The re-embed run builds the new vectors in `<live>-next`. The swap then moves them in:

    1. write `swap.json` (the target model): the swap is begun
    2. live    -> `<live>-old`
    3. `-next` -> live
    4. write the project's choice (`embedding.json`, atomically): the new vectors and the new model agree
    5. delete `swap.json`: the swap is verified
    6. delete `-old`

The old folder is the only copy of the old vectors until step 5, so it is deleted only after it. A failure (an exception) rolls
back to the old vectors and the old model at once. A death (power, kill) leaves a state `recover` reads on the next open:
a marker whose choice was written is finished; any other marker is undone; a live folder missing beside an `-old` is put back;
an `-old` beside a live folder and no marker is the leftover of a verified swap and is deleted."""
from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path
from typing import Callable

from fichero_server.core.atomic_json import write_json_atomic
from fichero_server.db.embedding_choice import read_choice, write_choice

logger = logging.getLogger(__name__)

MARKER = "swap.json"

#: Called after each step with its name; tests raise from it to fail (an Exception) or die (a BaseException) there.
_hook: Callable[[str], None] = lambda step: None  # noqa: E731


def folders(live: Path) -> tuple[Path, Path]:
    return live.with_name(live.name + "-next"), live.with_name(live.name + "-old")


def _roll_back(live: Path, nxt: Path, old: Path) -> None:
    """Put the old vectors back at the live path; the new ones wait in `-next` to be carried on."""
    if not old.exists():
        return  # the first rename never happened: nothing was moved
    if live.exists():  # the new vectors are live: step them aside
        if nxt.exists():
            shutil.rmtree(nxt)
        live.rename(nxt)
    old.rename(live)


def swap(package: Path, live: Path, target_model: str) -> None:
    """Make `-next` the live vectors and `target_model` the project's model, as one step that rolls back on failure."""
    nxt, old = folders(live)
    marker = package / MARKER
    previous = read_choice(package)
    live.mkdir(parents=True, exist_ok=True)
    write_json_atomic(marker, {"to": target_model})
    try:
        _hook("marked")
        live.rename(old)
        _hook("live-moved")
        nxt.rename(live)
        _hook("next-moved")
        write_choice(package, target_model)
        _hook("choice-written")
    except Exception:
        _roll_back(live, nxt, old)
        if previous is None:  # the choice goes back too: the old vectors and the old model agree
            (package / "embedding.json").unlink(missing_ok=True)
        else:
            write_choice(package, previous)
        marker.unlink(missing_ok=True)
        raise
    marker.unlink(missing_ok=True)
    _hook("verified")
    shutil.rmtree(old, ignore_errors=True)


def recover(package: Path, live: Path) -> str | None:
    """Leave the live vector folder whole after a swap a crash cut short. What it did, or None when there was nothing to do."""
    nxt, old = folders(live)
    marker = package / MARKER
    if marker.exists():
        try:
            target = json.loads(marker.read_text(encoding="utf-8")).get("to")
        except (OSError, ValueError):
            target = None
        if target and live.exists() and read_choice(package) == target:
            marker.unlink(missing_ok=True)  # the choice was written: the new vectors and model agree
            shutil.rmtree(old, ignore_errors=True)
            logger.warning("finished a vector swap a crash cut short (%s)", target)
            return "finished"
        _roll_back(live, nxt, old)
        marker.unlink(missing_ok=True)
        logger.warning("undid a vector swap a crash cut short")
        return "rolled back"
    if not live.exists() and old.exists():
        old.rename(live)
        logger.warning("restored the vectors a crash left at %s", old)
        return "restored"
    if old.exists():
        shutil.rmtree(old, ignore_errors=True)  # no marker: the swap was verified, only the cleanup was left
        return "cleaned"
    return None
