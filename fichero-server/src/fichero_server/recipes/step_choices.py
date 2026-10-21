"""The Start plan's per-step choices (`source.onboard.step-candidates-on-the-plan`, `source.onboard.step-choice-overrides-the-pick`).

For each step that has a choice of model (a reader of lines, a reader of pages, Correct) the plan lists the candidates from the
cards that fit, local and cloud, each with where it runs and what it needs; the one Set Up picked is marked, and so is the one
the person chose instead. A cloud candidate with no permission or no key is listed with what it needs, never hidden. The menu
is an OVERRIDE (`use_candidate` writes it, `overrides_without` takes it back): Set Up's pick stands until the person chooses another."""
from __future__ import annotations

import copy
from typing import Any

CHOICE_JOBS = ("read-a-line", "read-a-page", "correct")
_STAGE_WORDS = {"read-a-line": "Read lines", "read-a-page": "Read pages", "correct": "Correct"}


def _person_override(recipe: dict[str, Any], step_id: str) -> dict[str, Any] | None:
    return next((o for o in recipe.get("overrides") or []
                 if o.get("step") == step_id and o.get("scope") == "project" and o.get("folder_id") is None), None)


def _how(card: Any, job: str) -> str:
    """The way a candidate does the step, in the words the menu groups by."""
    cloud = str(card.runs_on).startswith("cloud:")
    if job == "correct":
        return "kraken-then-cloud-corrects" if cloud else "local-model"
    if job == "read-a-line":
        if cloud:
            return "cloud-reads-kraken-lines"
        return "kraken" if "kraken" in card.pin or str(card.id).startswith("kraken:") else "local-model"
    return "cloud-model" if cloud else "local-model"


def _needs(card: Any, *, may_leave: bool) -> list[dict[str, str]]:
    """What the candidate needs before it can run, each in words with the kind the app can act on."""
    out: list[dict[str, str]] = []
    if str(card.runs_on).startswith("cloud:"):
        provider = str(card.runs_on).split(":", 1)[1]
        if not may_leave:
            out.append({"kind": "permission", "words": "Allow pages to be sent to a cloud service for this project"})
        if str(card.id).endswith("@settings"):  # a provider with no row yet (remote_reader_cards)
            out.append({"kind": "key", "words": f"Add a {provider.capitalize()} key in Settings › AI"})
        provider_model = (card.pin.get("cloud"), card.pin.get("model"))
        if all(provider_model):
            from fichero_server.llm.spend import has_listed_price

            if not has_listed_price(*provider_model):  # accepted at Start (`accept_unpriced`), so it does not block the choice
                out.append({"kind": "price", "words": "No listed price: Start asks you to accept it, counted at an assumed price"})
    elif getattr(card, "installed", None) is False:
        out.append({"kind": "download", "words": "Download the model first"})
    return out


def _cost(card: Any, pages: int | None) -> dict[str, Any] | None:
    """The candidate's cost for the whole set before Start (an estimate from the price list; `TryCost`'s shape): free on this Mac,
    the price per page times the pages for a priced cloud model, unknown for one with no listed price, none before the pages are counted."""
    from fichero_server.recipes.assemble import _page_price

    if not str(card.runs_on).startswith("cloud:"):
        return {"value": 0.0, "basis": "estimate", "measured": False, "from": "free on this Mac"}
    price = _page_price(card)
    if not price:
        return {"value": None, "basis": "unknown", "measured": False, "from": "no listed price"}
    if not pages:
        return None
    return {"value": round(price * pages, 2), "basis": "estimate", "measured": False,
            "from": f"the price list, {pages:,} {'page' if pages == 1 else 'pages'}"}


def _candidate(card: Any, job: str, *, picked: str | None, recommended: str | None, may_leave: bool,
               pages: int | None = None) -> dict[str, Any]:
    needs = _needs(card, may_leave=may_leave)
    return {"card": card.id, "name": card.note.strip().rstrip(".") or card.id, "how": _how(card, job),
            "runs_on": card.runs_on, "local": not str(card.runs_on).startswith("cloud:"),
            "picked": card.id == picked, "recommended": card.id == recommended,
            "available": not [n for n in needs if n["kind"] != "price"], "needs": needs, "cost_usd": _cost(card, pages),
            "measured": ("CER %.1f%% on your pages" % (card.cer_measured_here * 100)
                         if card.cer_measured_here is not None else "not yet measured on your pages")}


def step_choices(recipe: dict[str, Any] | None, answers: dict[str, Any] | None, cards: list[Any], *, may_leave: bool,
                 pages: int | None = None) -> list[dict[str, Any]]:
    """One entry per choosable step of `recipe`: its candidates over `cards` (every card the finder knows, local and cloud)."""
    from fichero_server.recipes.discovery import step_candidates

    out: list[dict[str, Any]] = []
    for step in (recipe or {}).get("steps") or []:
        job = step.get("job")
        if job not in CHOICE_JOBS:
            continue
        override = _person_override(recipe or {}, step.get("id", ""))
        own = (step.get("card") or {}).get("id")
        picked = (override or {}).get("card") or own
        listed = step_candidates(cards, job, frozenset({picked} if picked else ()))
        # `recommended` is Set Up's pick, known only while it stands: under a person's choice the pick is not stored, so
        # nothing is marked (taking the choice back, use-setup-pick, shows it again) rather than guessing one.
        recommended = None if override else own
        out.append({"step": step.get("id"), "job": job, "name": _STAGE_WORDS.get(job, job), "picked": picked,
                    "chosen_by": "person" if override else "setup",
                    "candidates": [_candidate(c, job, picked=picked, recommended=recommended, may_leave=may_leave, pages=pages)
                                   for c in listed]})
    return out


def overrides_without(recipe: dict[str, Any] | None, step_id: str) -> list[dict[str, Any]]:
    """The recipe's overrides with the person's choice for `step_id` taken back, so assembling the recipe again lets Set Up's
    pick stand for that step (the others stay). ValueError, in words."""
    if not recipe:
        raise ValueError("this project has no recipe yet: run setup first")
    if not any(s.get("id") == step_id for s in recipe.get("steps") or []):
        raise ValueError(f"this project's recipe has no step {step_id!r}")
    if _person_override(recipe, step_id) is None:
        raise ValueError("Set Up's pick is already in use for that step")
    return [copy.deepcopy(o) for o in recipe.get("overrides") or []
            if (o.get("step"), o.get("scope"), o.get("folder_id")) != (step_id, "project", None)]
