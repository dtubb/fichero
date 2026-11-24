"""The gate a trained reader passes before it can be offered as a replacement (`distill.gate.one-rule`, #5337).

One rule from one function: the candidate's CER against the current reader's on the same held-out pages, with the
project's noise band. Better by more than the band: `better`; worse by more than the band: `worse` (kept, never
offered); inside it either way: `too close`; no figure: `not measured`. A reader with no verdict is never offered.
"""
from __future__ import annotations

from typing import Any

BETTER, TOO_CLOSE, WORSE, NOT_MEASURED = "better", "too close", "worse", "not measured"
NO_VERDICT = "Not measured: no verdict yet, so it is not offered as a replacement."


def not_measured(why: str) -> dict[str, Any]:
    return {"verdict": NOT_MEASURED, "words": f"not measured: {why}"}


def verdict(candidate_cer: float | None, current_cer: float | None, *, band: float, pages: int) -> dict[str, Any]:
    """The verdict and its words, `gain` being how far the candidate's CER is below the current one's."""
    if candidate_cer is None or current_cer is None or not pages:
        return not_measured("no held-out corrected pages")
    gain = current_cer - candidate_cer
    out = {"gain": round(gain, 6), "noise_band": band, "pages": pages, "against_cer": current_cer, "cer": candidate_cer}
    if gain > band:
        return {**out, "verdict": BETTER, "words": f"better by {gain * 100:.1f} points on {pages} pages"}
    if gain < -band:
        return {**out, "verdict": WORSE, "words": "worse: kept, not offered"}
    return {**out, "verdict": TOO_CLOSE, "words": "too close to call"}
