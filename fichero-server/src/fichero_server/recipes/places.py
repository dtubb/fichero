"""Where models may run (#5828, #5810's engine half; `source.onboard.first-launch-three-screens`).

Set Up Fichero asks once, for the whole app, which places the person allows: this Mac, another Mac of theirs, a cloud
AI service, ACENET, Hugging Face. The answer is an app setting (`models_may_run`), set by the audited action
`recipes.set_places`, and it CAPS every project: a project may be stricter, never looser. A project's `cloud_allowed` is its own
yes; pages go to a place only when the project said yes AND the app allows that place (`may_leave_to`), checked where
pages would leave.
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


def allows(place: str, places: list[str] | None = None) -> bool:
    """Whether the app allows `place`. Per place, never one flag: allowing another Mac opens neither the cloud nor
    Hugging Face Jobs nor the cluster (review 213)."""
    return place == THIS_MAC or place in (places if places is not None else get_places())


def may_leave_to(answers: dict[str, Any] | None, place: str) -> bool:
    """Whether a project's pages may go to `place`: the project said so AND the app allows the place. Read where pages
    would actually leave, never at read time, so no save can narrow a project's stored answer."""
    return bool((answers or {}).get("cloud_allowed")) and allows(place)


def this_mac_line(memory_gb: float) -> str:
    """What this Mac can run, from its real memory (the owner's words, 2026-10-19)."""
    gb = round(memory_gb)
    if memory_gb <= SMALL_MAC_GB:
        return (f"This Mac has {gb} GB of memory: enough for Kraken and Apple Vision, but too little for "
                "larger models. For difficult hands, allow another Mac, the cloud, or a cluster below.")
    return (f"This Mac has {gb} GB of memory: enough for the models made for your script, but not the largest AI "
            "models.")
