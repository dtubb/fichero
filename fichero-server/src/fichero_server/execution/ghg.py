"""Greenhouse gas of a job, from energy x grid intensity, always with its basis
(`activity.ghg.estimate-with-its-basis`, #5420). A figure that cannot be worked out is `unknown`, never 0."""
from __future__ import annotations

from typing import Any

UNKNOWN = {"grams": None, "basis": "unknown"}
_STRENGTH = {"measured": 0, "estimate": 1}  # a roll-up takes the weakest basis among its known parts


def estimate(*, power_watts: float | None, seconds: float | None, grid_g_per_kwh: float | None,
             measured: bool) -> dict[str, Any]:
    """Grams of CO2e for `power_watts` drawn over `seconds` where the grid emits `grid_g_per_kwh`.
    `measured` is True for this Mac's measured draw, False for a target's stated (rated) hardware."""
    if power_watts is None or seconds is None or grid_g_per_kwh is None:
        return dict(UNKNOWN)
    kwh = power_watts * seconds / 3_600_000
    return {"grams": round(kwh * grid_g_per_kwh, 6), "basis": "measured" if measured else "estimate"}


def roll_up(parts: list[dict[str, Any]]) -> dict[str, Any]:
    """The sum of a tree's known figures with the weakest basis among them; unknown parts are counted, not added."""
    known = [p for p in parts if p.get("grams") is not None]
    unknown_parts = len(parts) - len(known)
    if not known:
        return {**UNKNOWN, "unknown_parts": unknown_parts}
    basis = max((p["basis"] for p in known), key=lambda b: _STRENGTH.get(b, 1))
    return {"grams": round(sum(p["grams"] for p in known), 6), "basis": basis, "unknown_parts": unknown_parts}
