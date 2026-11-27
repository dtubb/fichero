"""Trusted coverage (#6970, `hands.metric.trusted-coverage`).

`trusted_coverage` takes one row per report-half line, `{"edits", "chars", "confidence"}`, orders the lines by
confidence (highest first) and, for every prefix, pools the character error (sum of edits over sum of reference
characters). `trusted_coverage` is the largest share of lines whose prefix has a pooled error of at most 2%; the
whole risk-coverage curve is returned beside it. Rows with no confidence at all give the string "no confidence";
a mix of present and missing confidences raises.
"""

from __future__ import annotations

THRESHOLD = 0.02


def trusted_coverage(rows: list[dict], threshold: float = THRESHOLD) -> dict:
    """`{"trusted_coverage": share | "no confidence", "risk_coverage": [{"coverage", "cer"}, ...]}`."""
    missing = [r for r in rows if r["confidence"] is None]
    if missing and len(missing) == len(rows):
        return {"trusted_coverage": "no confidence", "risk_coverage": []}
    if missing:
        raise ValueError(f"{len(missing)} of {len(rows)} lines have no confidence")
    ordered = sorted(rows, key=lambda r: -r["confidence"])
    curve, edits, chars, best = [], 0, 0, 0.0
    for k, r in enumerate(ordered, 1):
        edits += r["edits"]
        chars += r["chars"]
        point = {"coverage": round(k / len(ordered), 6), "cer": round(edits / chars, 6)}
        curve.append(point)
        if point["cer"] <= threshold:
            best = point["coverage"]
    return {"trusted_coverage": best, "risk_coverage": curve}
