"""The Start plan's per-step choices (`source.onboard.step-candidates-on-the-plan`, `source.onboard.step-choice-overrides-the-pick`).

For each step that has a choice of model (a reader of lines, a reader of pages, Correct) the plan lists the candidates from the
cards that fit, local and cloud, each with where it runs and what it needs; the one Set Up picked is marked, and so is the one
the person chose instead. A cloud candidate with no permission or no key is listed with what it needs, never hidden. The menu
is an OVERRIDE (`use_candidate` writes it, `overrides_without` takes it back): Set Up's pick stands until the person chooses another."""
from __future__ import annotations

import copy
from collections.abc import Callable
from typing import Any

#: The steps with a choice of model: the readers, Correct, and the two text steps (spaCy, Apple Intelligence, a model of the person's own,
#: a cloud model: `source.onboard.step-candidates-on-the-plan`, Test 13).
CHOICE_JOBS = ("read-a-line", "read-a-page", "correct", "translate-transliterate-normalise", "find-names-tag-words", "find-statements")
_STAGE_WORDS = {"read-a-line": "Read lines", "read-a-page": "Read pages", "correct": "Correct",
                "translate-transliterate-normalise": "Translate", "find-names-tag-words": "Find names",
                "find-statements": "Find statements"}


#: Where a card that is neither this Mac nor a cloud service runs, in the words the plan shows (never the internal id).
PLACE_WORDS = {"cluster": "a cluster", "gpu-service": "a GPU service"}

#: The choice kraken-then-cloud-corrects on the READ step's menu: its card id form, and what its Correct override says
#: (`source.recipe.kraken-reads-cloud-corrects-unsure`).
UNSURE_ID = "corrects-unsure:"
UNSURE_BECAUSE = "Kraken reads; chosen by you: a cloud model corrects only the lines Kraken is unsure of"
#: Typed fields on that Correct override (internal to the recipe, so no API change): `unsure` marks it as the unsure-lines choice,
#: `correct_was_on` records that Correct was already on in Set Up (the person's own answer), so taking the choice back leaves it on.
UNSURE_FIELD = "unsure"
CORRECT_WAS_ON_FIELD = "correct_was_on"


def _person_override(recipe: dict[str, Any], step_id: str) -> dict[str, Any] | None:
    return next((o for o in recipe.get("overrides") or []
                 if o.get("step") == step_id and o.get("scope") == "project" and o.get("folder_id") is None), None)


def unsure_card(recipe: dict[str, Any] | None) -> str | None:
    """The cloud card whose correction of Kraken's unsure lines the person chose (their Correct override says so), else None."""
    for step in (recipe or {}).get("steps") or []:
        if step.get("job") == "correct":
            o = _person_override(recipe or {}, step.get("id", ""))
            if o and o.get(UNSURE_FIELD) is True:
                return o.get("card")
    return None


def unsure_set_correct_on(recipe: dict[str, Any] | None) -> bool:
    """Whether the unsure-lines choice itself turned Correct on (False when the person had set the answer in Set Up first)."""
    for step in (recipe or {}).get("steps") or []:
        if step.get("job") == "correct":
            o = _person_override(recipe or {}, step.get("id", ""))
            if o and o.get(UNSURE_FIELD) is True:
                return o.get(CORRECT_WAS_ON_FIELD) is not True
    return False


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


def _cost(card: Any, pages: int | None, how: str = "") -> dict[str, Any] | None:
    """The candidate's cost for the whole set before Start (an estimate from the price list; `TryCost`'s shape): free on this Mac,
    the price per page times the pages for a priced cloud model, unknown for one with no listed price, none before the pages are counted.
    Only a card that runs on this Mac is free: a cluster or GPU service says its own words (no price here), never "free"."""
    from fichero_server.recipes.assemble import _page_price

    runs_on = str(card.runs_on)
    if runs_on == "this-mac":
        return {"value": 0.0, "basis": "estimate", "measured": False, "from": "free on this Mac"}
    if not runs_on.startswith("cloud:"):
        return {"value": None, "basis": "unknown", "measured": False, "from": f"runs on {PLACE_WORDS.get(runs_on, runs_on)}; no price is listed here"}
    price = _page_price(card)
    if not price:
        return {"value": None, "basis": "unknown", "measured": False, "from": "no listed price"}
    if not pages:
        return None
    count = f"{pages:,} {'page' if pages == 1 else 'pages'}"
    if how == "kraken-then-cloud-corrects":  # only the unsure lines are re-read, so the whole-page figure is the most it can cost
        return {"value": round(price * pages, 2), "basis": "upper bound", "measured": False,
                "from": f"the price list, at most {count} (only the unsure lines are sent)"}
    return {"value": round(price * pages, 2), "basis": "estimate", "measured": False, "from": f"the price list, {count}"}


def _candidate(card: Any, job: str, *, picked: str | None, recommended: str | None, may_leave: bool,
               pages: int | None = None, places_of: Callable[[Any], list[dict[str, Any]]] | None = None) -> dict[str, Any]:
    needs = _needs(card, may_leave=may_leave)
    return {"card": card.id, "name": card.note.strip().rstrip(".") or card.id, "how": _how(card, job),
            "runs_on": card.runs_on, "local": not str(card.runs_on).startswith("cloud:"),
            "picked": card.id == picked, "recommended": card.id == recommended,
            "available": not [n for n in needs if n["kind"] != "price"], "needs": needs, "places": places_of(card) if places_of else [], "cost_usd": _cost(card, pages, _how(card, job)),
            "measured": ("CER %.1f%% on your pages" % (card.cer_measured_here * 100)
                         if card.cer_measured_here is not None else "not yet measured on your pages")}


def step_choices(recipe: dict[str, Any] | None, answers: dict[str, Any] | None, cards: list[Any], *, may_leave: bool,
                 pages: int | None = None, places_of: Callable[[Any], list[dict[str, Any]]] | None = None) -> list[dict[str, Any]]:
    """One entry per choosable step of `recipe`: its candidates over `cards` (every card the finder knows, local and cloud);
    `places_of(card)` lists every place the card can run (`where_it_runs.places_it_can_run`), none when not given."""
    from fichero_server.recipes.discovery import step_candidates

    out: list[dict[str, Any]] = []
    bar = _certainty_bar(answers)
    steps = (recipe or {}).get("steps") or []
    kraken_reads = any(s.get("job") == "read-a-line" and _kraken(s) for s in steps)
    for step in steps:
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
        entries = [_candidate(c, job, picked=picked, recommended=recommended, may_leave=may_leave, pages=pages, places_of=places_of) for c in listed]
        chosen_by = "person" if override else "setup"
        if job == "read-a-line" and _kraken(step):
            # Kraken-then-a-cloud-correction is a way to read the lines too (`source.onboard.step-candidates-on-the-plan`): its own
            # card id form, so `use-candidate` on this step keeps Kraken as the reader and turns Correct on with that card.
            on = unsure_card(recipe)
            for c in step_candidates(cards, "correct"):
                if str(c.runs_on).startswith("cloud:"):
                    e = _candidate(c, "correct", picked=None, recommended=None, may_leave=may_leave, pages=pages, places_of=places_of)
                    e.update(card=UNSURE_ID + c.id, picked=c.id == on)
                    entries.append(e)
            if on:
                for e in entries:
                    e["picked"] = e["card"] == UNSURE_ID + on
                picked, chosen_by = UNSURE_ID + on, "person"
        out.append({"step": step.get("id"), "job": job, "name": _STAGE_WORDS.get(job, job), "picked": picked,
                    "chosen_by": chosen_by, "in_plan": True,
                    "wording": UNSURE_WORDS if job == "correct" and kraken_reads else None,
                    "certainty_bar": bar if job == "correct" and kraken_reads else None, "turn_on": None,
                    "candidates": entries})
    reads = any(s.get("job") in ("read-a-line", "read-a-page") for s in steps)
    if reads and not any(s.get("job") == "correct" for s in steps):
        # Where the person finds it (`source.recipe.kraken-reads-cloud-corrects-unsure`): Correct is not in the plan, but its cloud
        # candidates are listed with the way to turn it on (Set Up's own question), so Kraken-then-a-cloud-model is never hidden.
        # every cloud corrector the person has a row for is listed (`_offered_cards` makes a cloud vision reader one), a missing
        # key said in `needs`, so the option is found before a key is added.
        listed = [c for c in step_candidates(cards, "correct") if kraken_reads is False or str(c.runs_on).startswith("cloud:")]
        if listed:
            out.append({"step": "correct", "job": "correct", "name": _STAGE_WORDS["correct"], "picked": None, "chosen_by": "setup",
                        "in_plan": False, "wording": UNSURE_WORDS if kraken_reads else None, "certainty_bar": bar if kraken_reads else None,
                        "turn_on": {"answer": "correct_with_a_second_model", "value": True,
                                    "words": "Have a second model check the reading, in Set Up"},
                        "candidates": [_candidate(c, "correct", picked=None, recommended=None, may_leave=may_leave, pages=pages, places_of=places_of)
                                       for c in listed]})
    return out


#: What the Correct step is when Kraken reads (`source.recipe.kraken-reads-cloud-corrects-unsure`).
UNSURE_WORDS = "Kraken reads; a cloud model corrects only the lines Kraken is unsure of"


def _kraken(step: dict[str, Any]) -> bool:
    """Whether the step's reader is a Kraken reader (a Kraken model pin, or Kraken's repository record)."""
    pin = step.get("model") or {}
    return "kraken" in pin or "zenodo" in pin or str((step.get("card") or {}).get("id", "")).startswith("kraken:")


def _certainty_bar(answers: dict[str, Any] | None) -> float | None:
    """Set Up's `review_certainty_bar` answer as a number: Kraken's lines under it are the ones the cloud model corrects; None when the
    answer is the whole page (no bar chosen yet)."""
    raw = ((answers or {}).get("job_answers") or {}).get("review_certainty_bar")
    try:
        bar = float(raw)
    except (TypeError, ValueError):
        return None
    return bar if 0 < bar <= 1 else None


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
