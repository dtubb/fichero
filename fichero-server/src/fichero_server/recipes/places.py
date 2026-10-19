"""Where models may run (#5828, #5810's engine half; `source.onboard.first-launch-three-screens`).

Set Up Fichero asks once, for the whole app, which places the person allows: this Mac, another Mac of theirs, a cloud
AI service, ACENET, Hugging Face. The answer is an app setting (`models_may_run`), set by the audited action
`recipes.set_places`, and it CAPS every project: a project may be stricter, never looser. Pages leave this Mac for every
place but the first, so a project's `cloud_allowed` reads false unless some other place is allowed.
"""
from __future__ import annotations

import json
from typing import Any

SETTING_KEY = "models_may_run"
THIS_MAC = "this-mac"
PLACES = (THIS_MAC, "another-mac", "cloud", "acenet", "huggingface")
DEFAULT = (THIS_MAC,)
#: At or below this much memory the Mac is called small (the owner's text: "8 GB or less").
SMALL_MAC_GB = 8


def get_places() -> list[str]:
    """The allowed places; this Mac only until the person says otherwise (or the setting cannot be read)."""
    from fichero_server.db.app import get_app_db

    try:
        raw = get_app_db().get_setting(SETTING_KEY)
        said = json.loads(raw) if raw else None
    except Exception:  # noqa: BLE001 -- unreadable: the strictest answer, never a failed plan
        said = None
    return normalise(said)


def normalise(said: Any) -> list[str]:
    """The places in order, known ones only, this Mac always among them (it is where the app is)."""
    chosen = {p for p in (said or []) if p in PLACES} | {THIS_MAC}
    return [p for p in PLACES if p in chosen]


def set_places(places: list[str]) -> list[str]:
    from fichero_server.db.app import get_app_db

    kept = normalise(places)
    get_app_db().set_setting(SETTING_KEY, json.dumps(kept))
    return kept


def pages_may_leave(places: list[str] | None = None) -> bool:
    """Whether the app allows any place but this Mac."""
    return any(p != THIS_MAC for p in (places if places is not None else get_places()))


def cap(answers: dict[str, Any] | None) -> dict[str, Any] | None:
    """A project's answers under the app's setting: `cloud_allowed` is false unless the app allows a place off this Mac."""
    if not answers or not answers.get("cloud_allowed") or pages_may_leave():
        return answers
    return {**answers, "cloud_allowed": False}


def this_mac_line(memory_gb: float) -> str:
    """What this Mac can run, from its real memory (the owner's words, 2026-10-19)."""
    gb = round(memory_gb)
    if memory_gb <= SMALL_MAC_GB:
        return (f"This Mac has {gb} GB of memory: enough for Kraken and Apple's text recognition, but too little for "
                "larger models. For difficult hands, allow another Mac, the cloud, or a cluster below.")
    return (f"This Mac has {gb} GB of memory: enough for the models made for your script, but not the largest AI "
            "models.")
