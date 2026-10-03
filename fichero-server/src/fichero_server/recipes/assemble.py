"""Assembling a recipe from the setup answers and the model cards, by rule.

`source/models-chains-and-projects.md` sections 6 and 8: `source.onboard.deterministic-recipe`,
`source.onboard.purpose-sets-layers`, `source.recipe.cheapest-local-first`,
`source.recipe.volume-rule`, `source.recipe.embedder-by-language`. A pure function: the same
answers and the same cards always give the same recipe, and every choice names the facts it rests
on. A language model never decides anything here; it may only have filled in a card earlier, for a
person to confirm.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

#: Purpose -> the jobs it runs, in order (section 6). "Not sure yet" and "decipher" run nothing by
#: themselves: their tools are offered instead (handled by setup, not here).
PURPOSE_STEPS: dict[str, tuple[str, ...]] = {
    "transcribe": ("find-lines", "read-a-line", "correct"),
    "entities": ("find-lines", "read-a-line", "correct", "find-names-tag-words"),
    "search": ("find-lines", "read-a-line", "correct", "make-a-vector"),
    "knowledge-graph": ("find-lines", "read-a-line", "correct", "find-names-tag-words",
                        "work-out-dates", "find-statements", "make-a-vector"),
    "map-places": ("find-lines", "read-a-line", "correct", "find-names-tag-words",
                   "place-in-a-gazetteer", "make-a-vector"),
    "edit-corpus": ("find-lines", "read-a-line"),
    "decipher": (),
    "not-sure": (),
}

#: Jobs whose model must know the project's language (section 8, rule 3).
LANGUAGE_JOBS = frozenset({"correct", "translate-transliterate-normalise", "find-names-tag-words",
                           "find-statements", "make-a-vector"})
#: Of those, the ones where a model that lacks the language would rewrite it into another.
REWRITING_JOBS = frozenset({"correct", "translate-transliterate-normalise"})
#: Volume above which training is offered from the start (section 8, the volume rule).
TRAIN_OFFERED_FROM_PAGES = 5_000


@dataclass(frozen=True)
class Card:
    """The facts on a model card that the rules read (`source.model.*`)."""

    id: str
    pin: dict[str, Any]
    jobs: frozenset[str]
    scripts: frozenset[str] | None          # None: any script (a finder that does not read text)
    languages: frozenset[str] | None        # None: language-independent
    material: frozenset[str]                # handwriting, print, typescript
    runs_on: str = "this-mac"               # this-mac | cloud:<provider> | cluster | gpu-service
    open_licence: bool = True
    cost_per_page: float = 0.0
    pages_per_hour: float = 0.0
    carbon_g_per_page: float | None = None
    trainable: bool = False
    size_gb: float = 0.0
    memory_gb: float = 0.0
    cer_measured_here: float | None = None
    cer_published: float | None = None

    @property
    def local(self) -> bool:
        return self.runs_on == "this-mac"


@dataclass(frozen=True)
class Answers:
    purpose: str
    languages: frozenset[str]
    scripts: frozenset[str]
    material: str = "handwriting"
    pages: int = 0
    cloud_allowed: bool = False
    mac_memory_gb: float = 16.0


@dataclass
class Choice:
    job: str
    card: Card | None
    reasons: list[str] = field(default_factory=list)
    gap: str | None = None


def _hard_constraints(job: str, card: Card, a: Answers) -> str | None:
    """Why `card` cannot do `job` for this project, or None if it may."""
    if job not in card.jobs:
        return "its card does not name this job"
    if card.scripts is not None and not (a.scripts <= card.scripts):
        return "its card does not cover the project's script"
    if job in LANGUAGE_JOBS and card.languages is not None and not (a.languages <= card.languages):
        return "its card does not list the project's language"
    if job in REWRITING_JOBS and card.languages is None:
        return "a model that does not list the language would rewrite it into one it knows"
    if a.material == "handwriting" and card.material == frozenset({"print"}):
        return "it reads print only"
    if not card.open_licence:
        return "its licence is not open (accept it to use it)"
    if not card.local and card.runs_on.startswith("cloud:") and not a.cloud_allowed:
        return "it runs in the cloud and this project keeps pages on this Mac"
    if card.local and card.memory_gb > a.mac_memory_gb:
        return "this Mac does not have the memory to run it"
    return None


def _accuracy(card: Card) -> float:
    cer = card.cer_measured_here if card.cer_measured_here is not None else card.cer_published
    return cer if cer is not None else 1.0


def _rank_key(card: Card, a: Answers) -> tuple:
    """The fixed order (section 8): accuracy in one-point bands, then local before remote, cheaper,
    faster, lower carbon, trainable, smaller, and the card id so ties are deterministic. The
    material soft rule ranks a reader made for the project's material first."""
    band = int(_accuracy(card) * 100)
    return (
        band,
        0 if a.material in card.material else 1,
        0 if card.local else 1,
        card.cost_per_page,
        -card.pages_per_hour,
        card.carbon_g_per_page if card.carbon_g_per_page is not None else float("inf"),
        0 if card.trainable else 1,
        card.size_gb,
        card.id,
    )


def _choose(job: str, cards: list[Card], a: Answers) -> Choice:
    kept = [c for c in cards if _hard_constraints(job, c, a) is None]
    if not kept:
        named = [c for c in cards if job in c.jobs]
        why = "; ".join(sorted({f"{c.id}: {_hard_constraints(job, c, a)}" for c in named})) or "no card names this job"
        return Choice(job, None, gap=f"no model fits this step ({why})")
    # Cheapest and local first: start with the best LOCAL candidate; a remote one only when no
    # local one passes (the A/B, not the rules, decides any move to a costlier option).
    pool = [c for c in kept if c.local] or kept
    if job == "make-a-vector":
        # The embedder: the smallest local model whose card covers all the project's languages.
        pool = sorted(pool, key=lambda c: (c.size_gb, c.id))[:1]
    best = sorted(pool, key=lambda c: _rank_key(c, a))[0]
    reasons = [f"its card names this job; covers {', '.join(sorted(a.scripts))}"]
    if best.languages is not None and job in LANGUAGE_JOBS:
        reasons.append(f"lists {', '.join(sorted(a.languages))}")
    if a.material in best.material:
        reasons.append(f"made for {a.material}")
    acc = best.cer_measured_here if best.cer_measured_here is not None else best.cer_published
    if acc is not None:
        where = "on your pages" if best.cer_measured_here is not None else "as published"
        reasons.append(f"CER {acc * 100:.1f}% {where}")
    reasons.append("runs on this Mac, free" if best.local else f"runs on {best.runs_on}")
    if best.trainable:
        reasons.append("trainable on your corrections")
    return Choice(job, best, reasons=reasons)


def assemble(a: Answers, cards: list[Card]) -> dict[str, Any]:
    """The recipe for these answers, as recipe.yaml data, with each step's reasons and any gaps."""
    jobs = list(PURPOSE_STEPS.get(a.purpose, ()))
    if a.pages >= TRAIN_OFFERED_FROM_PAGES and jobs:
        jobs.append("train-a-model")
    steps, notes = [], []
    for job in jobs:
        if job == "train-a-model":
            steps.append({"id": job, "job": job, "layer": "train",
                          "offered_when": {"corrected_lines_at_least": 2000},
                          "settings": {"base": "read-a-line"}, "runs_on": "cluster",
                          "reasons": [f"{a.pages} pages: a reader trained on your corrections repays its training"]})
            continue
        choice = _choose(job, cards, a)
        step: dict[str, Any] = {"id": job, "job": job}
        if choice.card is None:
            step["gap"] = choice.gap
            notes.append(f"{job}: {choice.gap}")
        else:
            step["model"] = dict(choice.card.pin)
            step["runs_on"] = choice.card.runs_on
            step["reasons"] = choice.reasons
        steps.append(step)
    return {
        "fichero_recipe": 1,
        "id": f"generated/{a.purpose}-{'-'.join(sorted(a.languages))}-{'-'.join(sorted(a.scripts))}",
        "version": "0.1.0",
        "title": f"Generated for {a.purpose}: {', '.join(sorted(a.languages))} in {', '.join(sorted(a.scripts))}",
        "suits": {"scripts": sorted(a.scripts), "languages": sorted(a.languages), "material": [a.material]},
        "purposes": [a.purpose],
        "steps": steps,
        "gaps": notes,
    }
