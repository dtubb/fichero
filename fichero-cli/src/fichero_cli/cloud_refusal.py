"""A cloud refusal said in words with the way through (`ai.cloud.cli-refuses-in-words`, #6350): the engine serves the typed refusal
(`detail.refusal`, `llm/refusal.py`); the CLI prints its words, the figures, and each fix as the command or flag that does it. Exit
code 3 is "refused by a cloud rule", distinct from 1 (any error), so a script can tell a refusal from a failure."""

from __future__ import annotations

from typing import Any

EXIT_CODE = 3

_PROJECT_CAP_FLAG = {"cap-monthly": "--cap-usd", "cap-daily": "--daily-cap-usd", "cap-project": "--project-cap-usd", "cap-run": "--run-cap-usd"}
_APP_WHICH = {"cap-monthly": "monthly", "cap-daily": "daily"}


def _fix_line(fix: dict[str, Any], refusal: dict[str, Any]) -> str | None:
    kind, usd, scope = fix.get("kind"), fix.get("usd"), refusal.get("scope")
    if kind == "raise-to":
        if scope == "app" and refusal.get("kind") in _APP_WHICH:
            return f"raise the app's cap to ${usd:.2f}: fichero ai put-cloud-cap --which {_APP_WHICH[refusal['kind']]} --cap-usd {usd:.2f}"
        flag = _PROJECT_CAP_FLAG.get(refusal.get("kind", ""), "--cap-usd")
        return f"raise this project's cap to ${usd:.2f}: fichero recipes change-cloud-cap {flag} {usd:.2f}"
    if kind == "over-cap-once":
        return "run past the cap this once (nothing is saved, the spend is still booked): run it again with --over-cap-once"
    if kind == "allow-once":
        return "allow cloud for this run only (nothing is saved): run it again with --allow-cloud-once"
    if kind == "allow-project":
        return "allow cloud for this project: fichero recipes allow-cloud"
    if kind == "allow-everywhere":
        return "allow cloud for every project that has not answered: fichero recipes put-places (with cloud among the places)"
    if kind == "open-settings":
        return f"or change it in the app: Settings > AI ({fix.get('control')})"
    return None


def words(refusal: dict[str, Any]) -> str:
    """The refusal as text: what was refused, the figures when it is a cap, then each way through."""
    lines = [str(refusal.get("words") or "A cloud rule refused this call.")]
    if refusal.get("cap_usd") is not None:
        lines.append(f"  cap ${refusal['cap_usd']:.2f}, spent ${float(refusal.get('spent_usd') or 0):.2f}, "
                     f"this call or run up to ${float(refusal.get('estimate_usd') or 0):.2f}")
    ways = [line for fix in refusal.get("fixes") or [] if (line := _fix_line(fix, refusal))]
    if ways:
        lines.append("Ways through:")
        lines += [f"  - {line}" for line in ways]
    return "\n".join(lines)
