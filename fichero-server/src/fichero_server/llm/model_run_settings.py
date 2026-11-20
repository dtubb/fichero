"""Per-runtime run settings the Models and Compute window edits (`models.settings.run-knobs`, #6588).

Kept in the app settings under `models.run_settings` as {runtime: {knob: value}}; a knob not set is None and the engine's own
rule applies. Only knobs the engine reads are listed: Kraken's pages at once, threads a page, lines per batch and device.
A value outside its range is refused (ValueError), never clamped. `cost` says what a setting asks of this Mac: its memory
from the engine's own per-page figure, its time "—" until a measurement exists.
"""
from __future__ import annotations

import json
from typing import Any

SETTING_KEY = "models.run_settings"
#: runtime -> knob -> (kind, low, high or the allowed words)
KNOBS: dict[str, dict[str, tuple[Any, ...]]] = {
    "kraken": {"pages_at_once": ("int", 1, 16), "threads": ("int", 1, 64), "batch_size": ("int", 1, 64),
               "device": ("choice", ("auto", "cpu", "gpu"))},
}


def _stored() -> dict[str, dict[str, Any]]:
    from fichero_server.db.app import get_app_db

    raw = get_app_db().get_setting(SETTING_KEY)
    data = json.loads(raw) if raw else {}
    return data if isinstance(data, dict) else {}


def run_settings(runtime: str) -> dict[str, Any]:
    """The knobs the person set for `runtime`; every knob of the runtime is a key, None where unset. Unknown runtime: KeyError."""
    saved = _stored().get(runtime) or {}
    return {knob: saved.get(knob) for knob in KNOBS[runtime]}


def validate(runtime: str, values: dict[str, Any]) -> dict[str, Any]:
    """`values` checked against the runtime's knobs; ValueError naming the knob and its range. None un-sets a knob."""
    known = KNOBS[runtime]
    out: dict[str, Any] = {}
    for knob, value in values.items():
        if knob not in known:
            raise ValueError(f"{runtime} has no setting {knob!r}; it has {sorted(known)}")
        if value is None:
            out[knob] = None
            continue
        spec = known[knob]
        if spec[0] == "int":
            if isinstance(value, bool) or not isinstance(value, int) or not spec[1] <= value <= spec[2]:
                raise ValueError(f"{knob} must be a whole number from {spec[1]} to {spec[2]}, not {value!r}")
        elif value not in spec[1]:
            raise ValueError(f"{knob} must be one of {list(spec[1])}, not {value!r}")
        out[knob] = value
    return out


def save_run_settings(runtime: str, values: dict[str, Any]) -> dict[str, Any]:
    """Merge `values` into the runtime's saved knobs and return all of them."""
    changed = validate(runtime, values)
    from fichero_server.db.app import get_app_db

    data = _stored()
    data[runtime] = {**run_settings(runtime), **changed}
    get_app_db().set_setting(SETTING_KEY, json.dumps(data))
    return run_settings(runtime)


def cost(runtime: str, values: dict[str, Any]) -> dict[str, Any]:
    """What `values` ask of this Mac: `memory_bytes` is the model's own need plus each page read at once beyond it (the
    engine's per-page figure, the pages_at_once set or the engine's own number now); `seconds_per_page` is None, not
    measured here."""
    if runtime != "kraken":
        raise KeyError(runtime)
    from fichero_server.llm import kraken_runtime

    pages = values.get("pages_at_once") or kraken_runtime.pages_at_once(False)
    return {"memory_bytes": kraken_runtime.kraken_need_bytes() + max(0, pages - 1) * kraken_runtime._PAGE_BYTES,
            "seconds_per_page": None}
