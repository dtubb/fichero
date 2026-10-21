"""Where models may run (#5828, #5810's engine half; `source.onboard.first-launch-three-screens`).

Set Up Fichero asks once, for the whole app, which places the person allows: this Mac, another Mac of theirs, a cloud
AI service, ACENET, Hugging Face. The answer is an app setting (`models_may_run`), set by the audited action
the app's audited `PUT /api/recipes/places`, and it CAPS every project: a project may be stricter, never looser. A project's `cloud_allowed` is its own
yes; pages go to a place only when the project said yes AND the app allows that place (`may_leave_to`), checked where
pages would leave.
"""
from __future__ import annotations

import contextlib
import contextvars
import json
from pathlib import Path
from typing import Any, Iterator

SETTING_KEY = "models_may_run"
THIS_MAC = "this-mac"
PLACES = (THIS_MAC, "another-mac", "cloud", "acenet", "huggingface")
DEFAULT = (THIS_MAC,)
#: At or below this much memory the Mac is called small (the owner's text: "8 GB or less").
SMALL_MAC_GB = 8


def get_places() -> list[str] | None:
    """The allowed places, or None when the person has not answered (the setting is absent): unset is NOT ANSWERED,
    not "this Mac only", so an existing install behaves as before until its person answers (the house rule since 153).
    A setting that cannot be read is the strictest answer."""
    from fichero_server.db.app import get_app_db

    try:
        raw = get_app_db().get_setting(SETTING_KEY)
        return normalise(json.loads(raw)) if raw else None
    except Exception:  # noqa: BLE001 -- unreadable: the strictest answer, never a failed plan
        return [THIS_MAC]


def normalise(said: Any) -> list[str]:
    """The places in order, known ones only, this Mac always among them (it is where the app is)."""
    chosen = {p for p in (said or []) if p in PLACES} | {THIS_MAC}
    return [p for p in PLACES if p in chosen]


def set_places(places: list[str]) -> list[str]:
    from fichero_server.db.app import get_app_db

    kept = normalise(places)
    get_app_db().set_setting(SETTING_KEY, json.dumps(kept))
    return kept


def allows(place: str, places: list[str] | None = None) -> bool:
    """Whether the app allows `place`. Per place, never one flag: allowing another Mac opens neither the cloud nor
    Hugging Face Jobs nor the cluster (review 213). Not answered yet: no cap (the project's own yes still gates)."""
    said = places if places is not None else get_places()
    return place == THIS_MAC or said is None or place in said


def may_leave_to(answers: dict[str, Any] | None, place: str) -> bool:
    """Whether a project's pages may go to `place`: the project said so AND the app allows the place. Read where pages
    would actually leave, never at read time, so no save can narrow a project's stored answer."""
    return bool((answers or {}).get("cloud_allowed")) and allows(place)


#: Each place in the person's words, for a refusal.
PLACE_WORDS = {"another-mac": "another Mac of yours", "cloud": "a cloud AI service", "acenet": "ACENET",
               "huggingface": "Hugging Face"}


def refusal(place: str) -> str | None:
    """Why pages may not go to `place`, in words, or None when the app allows it: a route that sends pages on the
    request's own yes asks this too, whatever the request says (#5831, review 214)."""
    if allows(place):
        return None
    return (f"Your places do not include {PLACE_WORDS.get(place, place)}, so no pages are sent there. "
            "Allow it in Set Up Fichero… under where models may run.")


#: The project the work in hand is for (`ai.where.egress-at-every-call`, #5368): set where a run or a chat starts, read by the
#: model-call gate, so no call has to carry it. A ContextVar, so it follows the work into `asyncio` tasks and `to_thread`.
_project: contextvars.ContextVar[Path | None] = contextvars.ContextVar("fichero_egress_project", default=None)


@contextlib.contextmanager
def bound_project(library: str | Path | None) -> Iterator[None]:
    """Model calls inside this block are made for the project at `library` (None: for no project)."""
    token = _project.set(Path(library) if library else None)
    try:
        yield
    finally:
        _project.reset(token)


#: A scratch copy of some pages that a try runs on (`recipes/samples._run_one`) -> the real project it is a try for. The copy has
#: no Set Up of its own, so a call made for it is judged by, and its spend counted against, the real project.
_scratch_of: dict[Path, Path] = {}


@contextlib.contextmanager
def scratch_of(scratch: str | Path, real: str | Path) -> Iterator[None]:
    """For the length of the block, work bound to the folder `scratch` is for the project at `real`."""
    key = Path(scratch)
    _scratch_of[key] = Path(real)
    try:
        yield
    finally:
        _scratch_of.pop(key, None)


def bound_library() -> Path | None:
    """The project the work in hand is for: the bound folder, or the real project when that folder is a try's scratch copy."""
    bound = _project.get()
    return _scratch_of.get(bound, bound) if bound is not None else None


def project_refusal(place: str) -> str | None:
    """Why the bound project's own rule keeps pages from `place`, in words, or None. A project that saved a Set Up and did not
    say its pages may leave this Mac keeps them here (the start-time rule, `may_leave_to`, read at the call); a project with no
    saved Set Up, and a call made for no project, are capped by the app's places alone."""
    library = bound_library()
    if library is None or place == THIS_MAC:
        return None
    from fichero_server.recipes.project import read_project_setup

    try:
        answers = read_project_setup(library)["answers"]
    except Exception:  # noqa: BLE001 -- an unreadable Set Up is the strictest answer, as for the app's places
        answers = {}
    if answers is None or answers.get("cloud_allowed"):
        return None
    return (f"This project's Set Up says its pages stay on this Mac, so no pages are sent to {PLACE_WORDS.get(place, place)}. "
            "Change it in the project's Set Up.")


def this_mac_line(memory_gb: float) -> str:
    """What this Mac can run, from its real memory (the owner's words, 2026-10-19)."""
    gb = round(memory_gb)
    if memory_gb <= SMALL_MAC_GB:
        return (f"This Mac has {gb} GB of memory: enough for Kraken and Apple Vision, but too little for "
                "larger models. For difficult hands, allow another Mac, the cloud, or a cluster below.")
    return (f"This Mac has {gb} GB of memory: enough for the models made for your script, but not the largest AI "
            "models.")
