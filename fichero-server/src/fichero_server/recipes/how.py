"""How do you want to run this: the four questions Set Up asks first (`designer.how.*`, #6052).

Where the work runs, which kind of model, what matters most, and (shown, never asked) what the person has. The engine owns the options,
their consequences and the card the answers propose; the app draws what it is given. Saved as `answers.how` =
`{places: [...], model_kind, matters}`. Privacy never writes `cloud_allowed`: it only leaves the cloud question unanswered."""
from __future__ import annotations

from typing import Any

#: (id, name, consequence, the app place(s) that allow it). A place the app does not allow is listed greyed with its reason.
PLACES: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    ("this-mac", "This Mac", "Your pages stay on this Mac.", ("this-mac",)),
    ("another-mac", "Another machine of mine", "Your pages leave this Mac for a machine you own.", ("another-mac",)),
    ("cluster", "A cluster", "Your pages go to the cluster's administrators.", ("acenet", "huggingface")),
    ("cloud", "The cloud", "Your pages go to a company.", ("cloud",)),
)
MODEL_KINDS: tuple[tuple[str, str, str], ...] = (
    ("small", "Small local models", "Read only what is on the line: free, slower, and may misread a word."),
    ("large", "Large vision-language models", "Read fluently: cost per page, and may invent or regularise text."),
    ("compare", "Let Fichero compare and choose", "Fichero tries them on your pages and picks (the default)."),
)
DEFAULT_MODEL_KIND = "compare"
MATTERS: tuple[str, ...] = ("speed", "cost", "quality", "privacy")
#: A large model that runs on this Mac needs about this much memory. ponytail: one number, the model table decides once it exists.
LARGE_LOCAL_GB = 32
#: Teaching a small model pays from this many pages (`source.recipe.volume-rule`).
LARGE_ARCHIVE_PAGES = 5000


def offered_places(allowed: list[str] | None) -> list[dict[str, Any]]:
    """Each place with whether the app allows it and, when not, the engine's reason: greyed, never hidden."""
    from fichero_server.recipes import places

    out = []
    for pid, name, consequence, app_places in PLACES:
        shut = [p for p in app_places if not places.allows(p, allowed)]
        ok = len(shut) < len(app_places)  # a cluster tick is open when either of its places is
        reason = (f"Your places do not include {places.PLACE_WORDS.get(shut[0], shut[0])}, so no pages are sent there. "
                  "Allow it in Set Up Fichero… under where models may run.") if not ok else None
        out.append({"id": pid, "name": name, "consequence": consequence, "allowed": ok, "reason": reason})
    return out


def model_kind_options(*, cloud_allowed: bool, memory_gb: int | None) -> list[dict[str, Any]]:
    """The three kinds; the large one is greyed, with its reason, when the cloud is not allowed and this Mac cannot run one."""
    can_run = memory_gb is not None and memory_gb >= LARGE_LOCAL_GB
    out = []
    for kid, name, consequence in MODEL_KINDS:
        blocked = kid == "large" and not cloud_allowed and not can_run
        out.append({"id": kid, "name": name, "consequence": consequence, "allowed": not blocked,
                    "reason": "The cloud is not allowed and this Mac does not have the memory to run one." if blocked else None})
    return out


def default_matters(chosen_places: list[str] | None) -> str | None:
    """Privacy when only this Mac is ticked; otherwise nothing is pre-filled."""
    return "privacy" if chosen_places == ["this-mac"] else None


def normalise(how: Any) -> tuple[dict[str, Any], list[str]]:
    """(the answers kept in the places' order, the refusals in words). Unknown values are kept so reading never fails."""
    if not isinstance(how, dict):
        return {}, [f"How you want to run this is a mapping of question to answer, not {how!r}."]
    out, problems = dict(how), []
    if "places" in out:
        ids = [p[0] for p in PLACES]
        said = list(dict.fromkeys(out["places"] if isinstance(out["places"], list) else [out["places"]]))
        unknown = [p for p in said if p not in ids]
        if unknown:
            problems.append(f"Work runs on {', '.join(ids)}; not {', '.join(map(repr, unknown))}.")
        out["places"] = [p for p in ids if p in said] + unknown
    for key, valid in (("model_kind", [k[0] for k in MODEL_KINDS]), ("matters", list(MATTERS))):
        if out.get(key) is not None and out[key] not in valid:
            problems.append(f"{key.replace('_', ' ').capitalize()} is {', '.join(valid)}; not {out[key]!r}.")
    return out, problems


def proposed_card(how: dict[str, Any] | None, pages: int) -> str | None:
    """The route card the answers propose (`designer.how.answers-pick-the-card`): a, b, c or d (section 8), or None when they say nothing."""
    how = how or {}
    places, matters = how.get("places") or [], how.get("matters")
    if matters == "privacy" or places == ["this-mac"]:
        return "d"
    if "cluster" in places and matters == "cost":
        return "b"
    if "cloud" in places:
        return "a" if pages >= LARGE_ARCHIVE_PAGES else ("c" if matters == "quality" else None)
    return None
