"""The defaults table: the answers -> the recipe's defaults, each saying why, the person always winning (`designer.defaults.*`, #6052).

One vendored table (`seed/defaults-by-answers.yaml`). `resolve` is pure: it reads the answers and writes nothing, so a proposal (a cap)
is only ever proposed. Wiring it into `assemble.py` is the next slice; until then the stage pages and Ready can ask the engine for it."""
from __future__ import annotations

import math
from functools import lru_cache
from pathlib import Path
from typing import Any

SEED = Path(__file__).parent / "seed" / "defaults-by-answers.yaml"
USUAL = "Fichero's usual default"
#: What the person's choice can override, and what `resolve` returns for each.
KEYS = ("steps", "prepare", "model_kind", "review", "cap")


@lru_cache(maxsize=1)
def table() -> dict[str, Any]:
    import yaml

    return yaml.safe_load(SEED.read_text(encoding="utf-8"))


def _where(how: dict[str, Any]) -> str:
    places = how.get("places") or []
    return "cloud" if "cloud" in places else "cluster" if "cluster" in places else "this-mac"


def _matches(when: dict[str, Any] | None, facts: dict[str, Any]) -> bool:
    for key, want in (when or {}).items():
        have = facts.get(key)
        if isinstance(want, list):
            if not set(want) & set(have if isinstance(have, list) else [have]):
                return False
        elif have != want:
            return False
    return True


def _facts(answers: dict[str, Any], pages: int) -> dict[str, Any]:
    from fichero_server.recipes.how import LARGE_ARCHIVE_PAGES

    how = answers.get("how") or {}
    return {"material": answers.get("materials") or [], "where": _where(how), "matters": how.get("matters"),
            "large": pages >= LARGE_ARCHIVE_PAGES, "condition": answers.get("condition") or []}


def base_row(facts: dict[str, Any]) -> dict[str, Any]:
    """The one base row these facts hit: the first whose `when` matches, else the fallback."""
    rows = table()["base"]
    return next(r for r in rows if r.get("when") and _matches(r["when"], facts)) if any(
        r.get("when") and _matches(r["when"], facts) for r in rows) else rows[-1]


def resolve(answers: dict[str, Any] | None, pages: int = 0) -> dict[str, Any]:
    """`{steps, prepare, model_kind, review, cap, why: {key: {value, because, why}}, rows}`; reads, never writes."""
    answers = answers or {}
    facts = _facts(answers, pages)
    base = base_row(facts)
    out: dict[str, Any] = {"steps": list(base["steps"]), "prepare": [], "model_kind": base["model_kind"], "review": base["review"],
                           "cap": base["cap"], "rows": [base["id"]]}
    because = [", ".join(filter(None, [*facts["material"][:1], facts["matters"], facts["where"].replace("-", " ")]))]
    why = {k: {"why": base["why"], "because": because[0]} for k in ("steps", "model_kind", "review", "cap")} if base.get("why") else {}
    for cid in facts["condition"]:
        add = table()["adds"].get(cid)
        if add is None:
            continue
        out["rows"].append(f"add:{cid}")
        for step in add.get("steps", []):
            if step not in out["steps"]:
                out["steps"].append(step)
        for op in add.get("prepare", []):
            if op not in out["prepare"]:
                out["prepare"].append(op)
        if "review" in add:
            out["review"] = add["review"]
        if "cap" in add:
            out["cap"] = add["cap"]
        reason = {"why": add["why"], "because": cid.replace("-", " ")}
        for key in ("prepare", "steps", "review", "cap"):
            if add.get(key) is not None and key != "prepare" or (key == "prepare" and add.get("prepare")):
                why[key] = reason
    out["why"] = why
    return out


def says_why(defaults: dict[str, Any], key: str) -> str:
    """The grey line under a default: "chosen because: faded ink, this Mac only", or Fichero's usual default."""
    entry = (defaults.get("why") or {}).get(key)
    return f"{entry['why']} (chosen because: {entry['because']})" if entry and entry.get("because") else USUAL


def with_choices(defaults: dict[str, Any], chosen: dict[str, Any] | None) -> dict[str, Any]:
    """The person wins: a choice stays whatever the answers now say; where the table now suggests something else it is offered beside it."""
    chosen = {k: v for k, v in (chosen or {}).items() if k in KEYS}
    effective = {k: chosen.get(k, defaults.get(k)) for k in KEYS}
    offers = [{"key": k, "yours": v, "suggested": defaults.get(k),
               "words": f"Your answers now suggest {defaults.get(k)}; keep {v}?"}
              for k, v in chosen.items() if v != defaults.get(k)]
    return {"effective": effective, "offers": offers}


def cap_proposal(defaults: dict[str, Any], estimate_usd: float | None) -> dict[str, Any]:
    """The cap the table proposes (`designer.path.caps-proposed-not-written`): a figure to show, never written; the person confirms it."""
    kind = defaults.get("cap")
    if kind in (None, "none") or estimate_usd is None:
        return {"kind": kind, "usd": None}
    return {"kind": kind, "usd": float(math.ceil(estimate_usd)) if kind == "estimate-rounded" else round(estimate_usd, 2)}
