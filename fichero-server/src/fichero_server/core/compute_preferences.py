"""How hard local model work may push this Mac, and on which processor (set by the person).

Two choices, kept in the app settings and overridable by environment for test runs:

* ``priority``: ``balanced`` (the default: utility QoS, torch threads capped at about half the
  machine, the Mac stays usable while a page is read), ``fast`` (no throttle, every core: for a
  person who wants the run done, or a test), ``background`` (background QoS and fewer threads: for
  work nobody is waiting on).
* ``device``: ``auto`` (Apple's GPU when torch has it, else the CPU), ``cpu`` or ``gpu``.

``FICHERO_COMPUTE_PRIORITY`` / ``FICHERO_COMPUTE_DEVICE`` win over the setting, so a test run can go
as fast as possible without changing the person's choice. Read by Kraken now; the one job model
(`ui/activity-and-automatic-work.md`) reads the same preferences for every heavy kind.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Literal

logger = logging.getLogger(__name__)

SETTING_KEY = "compute.preferences"
Priority = Literal["fast", "balanced", "background"]
Device = Literal["auto", "cpu", "gpu"]
PRIORITIES: tuple[str, ...] = ("fast", "balanced", "background")
DEVICES: tuple[str, ...] = ("auto", "cpu", "gpu")
DEFAULTS = {"priority": "balanced", "device": "auto"}


def stored_preferences() -> dict[str, str]:
    """The person's saved choice (defaults where unset or unreadable)."""
    try:
        from fichero_server.db.app import get_app_db

        raw = get_app_db().get_setting(SETTING_KEY)
    except Exception as exc:  # noqa: BLE001 -- a settings read failure must never stop a page
        logger.warning("could not read %s: %s", SETTING_KEY, exc)
        raw = None
    saved = json.loads(raw) if raw else {}
    return {
        "priority": saved.get("priority") if saved.get("priority") in PRIORITIES else DEFAULTS["priority"],
        "device": saved.get("device") if saved.get("device") in DEVICES else DEFAULTS["device"],
    }


def compute_preferences() -> dict[str, str]:
    """What applies now: the environment's override, else the saved choice."""
    prefs = stored_preferences()
    for key, env, allowed in (("priority", "FICHERO_COMPUTE_PRIORITY", PRIORITIES),
                              ("device", "FICHERO_COMPUTE_DEVICE", DEVICES)):
        value = os.environ.get(env, "").strip().lower()
        if value in allowed:
            prefs[key] = value
    return prefs


def save_preferences(priority: str, device: str) -> dict[str, str]:
    if priority not in PRIORITIES or device not in DEVICES:
        raise ValueError(f"priority must be one of {PRIORITIES} and device one of {DEVICES}")
    from fichero_server.db.app import get_app_db

    get_app_db().set_setting(SETTING_KEY, json.dumps({"priority": priority, "device": device}))
    return {"priority": priority, "device": device}


def apply_to_this_thread(priority: str) -> int:
    """Set the calling thread's priority for model work; returns the torch thread count to use."""
    from fichero_server.core.background_compute import (
        cpu_count,
        embed_threads,
        set_background_qos,
        set_utility_qos,
    )

    if priority == "fast":
        return cpu_count()
    if priority == "background":
        set_background_qos()
        return max(1, embed_threads() // 2)
    set_utility_qos()
    return max(1, embed_threads())


def torch_accelerator(device: str) -> str:
    """Kraken/Lightning's accelerator name for the chosen device."""
    if device == "cpu":
        return "cpu"
    try:
        import torch

        has_gpu = torch.backends.mps.is_available()
    except Exception:  # noqa: BLE001 -- no torch, or no MPS: the CPU it is
        has_gpu = False
    return "mps" if has_gpu else "cpu"
