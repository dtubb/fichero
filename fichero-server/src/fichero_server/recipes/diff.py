"""What re-assembling a project's recipe from changed answers would change, step by step
(`source.onboard.regen-shows-diff`, #4951). Pure: two recipes in, the changes out; nothing is written."""
from __future__ import annotations

from typing import Any

#: The step fields a person sees change: the model it runs and its settings.
_COMPARED = ("model", "settings")


def _title(step: dict[str, Any]) -> str:
    return step.get("title") or step["id"]


def diff_recipes(saved: dict | None, fresh: dict | None) -> list[dict[str, Any]]:
    """Each step the fresh assembly adds, takes out, or runs differently from the saved recipe, in step order (the
    fresh recipe's first, then the ones taken out). A step the person set by hand is the saved recipe's own model, which
    the assembly keeps, so it shows no change."""
    old = {s["id"]: s for s in (saved or {}).get("steps") or []}
    new = {s["id"]: s for s in (fresh or {}).get("steps") or []}
    out: list[dict[str, Any]] = []
    for sid, step in new.items():
        was = old.get(sid)
        if was is None:
            out.append({"step": sid, "kind": "added", "words": f"{_title(step)} would be added", "was": None,
                        "now": step.get("model")})
            continue
        changed = [f for f in _COMPARED if (was.get(f) or None) != (step.get(f) or None)]
        if changed:
            what = " and ".join("its model" if f == "model" else "its settings" for f in changed)
            out.append({"step": sid, "kind": "changed", "words": f"{_title(step)}: {what} would change",
                        "was": was.get("model"), "now": step.get("model")})
    for sid, was in old.items():
        if sid not in new:
            out.append({"step": sid, "kind": "removed", "words": f"{_title(was)} would be taken out",
                        "was": was.get("model"), "now": None})
    return out
