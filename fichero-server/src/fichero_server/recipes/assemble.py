"""Assembling a recipe from the setup answers and the model cards, by rule.

`source/models-chains-and-projects.md` sections 6, 7b and 8: `source.onboard.deterministic-recipe`,
`source.onboard.purpose-sets-layers`, `source.onboard.material-any-mix`, `source.onboard.says-no-model`,
`source.recipe.cheapest-local-first`, `source.recipe.volume-rule`, `source.recipe.embedder-by-language`.
A pure function: the same answers and the same cards always give the same recipe, and every choice
names the facts it rests on. A language model never decides anything here; it may only have filled
in a card earlier, for a person to confirm.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

_TRANSCRIBE = ("find-lines", "read-a-line", "correct")

#: Purpose -> the jobs it runs (section 7b, screen 2). A project ticks any combination; its recipe is
#: the union of their jobs, each once, in `STEP_ORDER`. "Not sure yet" and "decipher" run nothing by
#: themselves: their tools are offered instead (handled by setup, not here). Two rows go beyond the
#: spec's table so the recipe check passes: dates need names (`work-out-dates` takes mentions), so
#: Catalogue finds names; a table's cells are read line by line, so Tables finds lines.
PURPOSE_STEPS: dict[str, tuple[str, ...]] = {
    "transcribe": _TRANSCRIBE,
    "entities": (*_TRANSCRIBE, "find-names-tag-words"),
    "search": (*_TRANSCRIBE, "make-a-vector"),
    "statements": (*_TRANSCRIBE, "find-names-tag-words", "find-statements"),
    "knowledge-graph": (*_TRANSCRIBE, "find-names-tag-words", "work-out-dates", "find-statements",
                        "link-to-authorities", "make-a-vector"),
    "map-places": (*_TRANSCRIBE, "find-names-tag-words", "place-in-a-gazetteer"),
    "translate-normalise": (*_TRANSCRIBE, "translate-transliterate-normalise"),
    "quotations": (*_TRANSCRIBE, "pull-out-passages"),
    "catalogue": (*_TRANSCRIBE, "find-names-tag-words", "work-out-dates", "describe-for-the-catalogue"),
    "tables": ("find-regions", "find-lines", "find-a-tables-cells", "read-a-line", "extract-to-a-table"),
    "edit-corpus": ("find-lines", "read-a-line"),
    "decipher": (),
    "not-sure": (),
}

#: How setup offers each purpose: its label, and whether it runs by itself ("just do it") or offers
#: its tools first. One list, read by setup, the Inspector and the manual (`source.onboard.purpose-first`).
PURPOSES: dict[str, tuple[str, str]] = {
    "transcribe": ("Just transcribe", "Read every page into text you can correct."),
    "entities": ("People, places and things", "Transcribe, then find the names in the text."),
    "search": ("Search my sources", "Transcribe, then make the text searchable by meaning."),
    "statements": ("Statements", "Transcribe, then find who did what to whom, each tied to its line."),
    "knowledge-graph": ("The full knowledge graph",
                        "Names, dates and statements, linked into one graph you can question."),
    "map-places": ("Map places", "Find the places in the text and put them on a map."),
    "translate-normalise": ("Translate or normalise",
                            "Transcribe, then translate, transliterate or normalise the spelling."),
    "quotations": ("Gather quotations", "Transcribe, then pull out the passages you are looking for."),
    "catalogue": ("Catalogue my sources", "Transcribe, then describe each source for the catalogue."),
    "tables": ("Tables and forms", "Find each table's cells, read them, and gather the rows into a table."),
    "edit-corpus": ("Edit a corpus", "Lines and readings to edit by hand; nothing runs by itself after."),
    "decipher": ("Decipher a script", "Tools for signs not yet read; nothing runs by itself."),
    "not-sure": ("Not sure yet", "Import first; the tools are offered when you want them."),
}
assert set(PURPOSES) == set(PURPOSE_STEPS)
#: Purposes that offer tools rather than running by themselves after Start (section 7b, screen 7).
TOOL_PURPOSES = frozenset({"edit-corpus", "decipher", "not-sure"})
#: The kinds of material setup offers as checkboxes, in the order the default reader is taken from.
MATERIALS: tuple[str, ...] = ("handwriting", "print", "typescript")
#: Jobs that read the material: they get one reader per kind of material ticked.
READING_JOBS = frozenset({"read-a-line", "read-a-page"})

#: Jobs whose model must know the project's language (section 8, rule 3).
LANGUAGE_JOBS = frozenset({"correct", "translate-transliterate-normalise", "find-names-tag-words",
                           "find-statements", "make-a-vector"})
#: Of those, the ones where a model that lacks the language would rewrite it into another.
REWRITING_JOBS = frozenset({"correct", "translate-transliterate-normalise"})
#: Volume above which training is offered from the start (section 8, the volume rule).
TRAIN_OFFERED_FROM_PAGES = 5_000
#: Memory left for macOS, the app and the engine when a model is resident (the 8 GB Air taught us).
MEMORY_HEADROOM_GB = 2.0


#: Every registered job, in the order a recipe runs them (the registry's step order): a ticked
#: purpose's jobs, and any job ticked on its own, are sorted by it. A test pins that it covers the
#: whole job registry, so a new job cannot be ticked without a place in the order.
STEP_ORDER: tuple[str, ...] = (
    "prepare-the-image", "split-pages", "find-documents-in-a-folder", "find-regions", "find-lines",
    "put-in-order", "refine-shapes", "find-signs", "find-a-tables-cells", "read-a-line", "read-a-page",
    "tie-text-to-lines", "transcribe-speech", "correct", "trace-a-drawing", "identify-signs",
    "translate-transliterate-normalise", "split-into-entries", "find-names-tag-words", "work-out-dates",
    "find-statements", "link-to-authorities", "place-in-a-gazetteer", "pull-out-passages",
    "describe-for-the-catalogue", "extract-to-a-table", "make-a-vector", "train-a-model", "check",
    "export", "publish",
)
assert all(list(s) == sorted(s, key=STEP_ORDER.index) for s in PURPOSE_STEPS.values())
#: The jobs a layer added later can turn on (`source.onboard.add-layer`), in order.
LAYER_STEPS: tuple[str, ...] = ("find-lines", "read-a-line", "correct", "find-names-tag-words", "work-out-dates",
                                "find-statements", "place-in-a-gazetteer", "make-a-vector")


def purpose_jobs(purposes) -> list[str]:
    """The union of these purposes' jobs, each once, in step order (`source.onboard.purpose-sets-layers`)."""
    return sorted({j for p in purposes for j in PURPOSE_STEPS.get(p, ())}, key=STEP_ORDER.index)


def layer_jobs(layer: str) -> tuple[str, ...]:
    """The jobs a layer turns on, in order: the assembled jobs whose registry entry names that layer."""
    from fichero_server.recipes.jobs import get_job

    return tuple(j for j in LAYER_STEPS if (job := get_job(j)) is not None and job.layer == layer)


def addable_layers() -> list[str]:
    """The layers a project can add later: those the rules can assemble a step for."""
    from fichero_server.recipes.jobs import get_job

    return list(dict.fromkeys(get_job(j).layer for j in LAYER_STEPS))


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
    licence: str = ""
    note: str = ""
    #: False when the card's runtime is not in this build (its seed row says `runs_here: false`): never a
    #: candidate for the recipe, but the bake-off names it (Tesseract, `source.onboard.bakeoff-tesseract-baseline`).
    runs_here: bool = True
    #: Where the card came from (#5519): `shipped` (the seed), `installed` (made from an installed model's
    #: own metadata, `made_from: metadata`), `kraken-repository` (its record in Kraken's repository on
    #: Zenodo) or `hugging-face` (a Hub search result).
    source: str = "shipped"
    #: Why discovery offers it, in words: what was found where, and what its record states.
    offered_because: str = ""

    @property
    def local(self) -> bool:
        return self.runs_on == "this-mac"


@dataclass(frozen=True)
class Answers:
    """Setup's answers as the rules read them. `purposes` and `materials` are lists (section 7b);
    `purpose` and `material` are the single answers of a project saved before 2026-10-05 and read
    as a list of one."""

    purpose: str = ""
    languages: frozenset[str] = frozenset()
    scripts: frozenset[str] = frozenset()
    material: str = ""
    pages: int = 0
    cloud_allowed: bool = False
    mac_memory_gb: float = 16.0
    #: Layers the person added beyond the purposes' (`source.onboard.add-layer`).
    layers: frozenset[str] = frozenset()
    purposes: tuple[str, ...] = ()
    materials: tuple[str, ...] = ()
    #: Jobs ticked on their own, beyond the purposes' (section 7b: every job is a checkbox).
    jobs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        # In the order setup offers them, so the same purposes ticked in any order give the same recipe.
        given = {*self.purposes, *((self.purpose,) if self.purpose else ())}
        purposes = tuple(p for p in PURPOSES if p in given) + tuple(sorted(given - set(PURPOSES)))
        materials = tuple(m for m in MATERIALS if m in {*self.materials, self.material}) or ("handwriting",)
        object.__setattr__(self, "purposes", purposes)
        object.__setattr__(self, "materials", materials)
        object.__setattr__(self, "purpose", purposes[0] if len(purposes) == 1 else "")
        object.__setattr__(self, "material", materials[0])


@dataclass
class Choice:
    job: str
    card: Card | None
    reasons: list[str] = field(default_factory=list)
    gap: str | None = None
    problem: dict[str, Any] | None = None


#: The hard constraints, in the order they are tried; a refused card names the first it fails. The
#: code is what setup shows (in words, with a fix), the raw reason what the Inspector and log keep.
_CONSTRAINTS = ("no-model-for-job", "no-model-for-script", "no-model-for-language", "no-model-for-language",
                "no-reader-for-material", "licence-not-accepted", "cloud-not-allowed", "not-enough-memory")


def _refusal(job: str, card: Card, a: Answers, material: str) -> tuple[str, str] | None:
    """(code, raw reason) for why `card` cannot do `job` for this project, or None if it may."""
    if job not in card.jobs:
        return "no-model-for-job", "its card does not name this job"
    if card.scripts is not None and not (a.scripts <= card.scripts):
        return "no-model-for-script", "its card does not cover the project's script"
    if job in LANGUAGE_JOBS and card.languages is not None and not (a.languages <= card.languages):
        return "no-model-for-language", "its card does not list the project's language"
    if job in REWRITING_JOBS and card.languages is None:
        return "no-model-for-language", "a model that does not list the language would rewrite it into one it knows"
    if material == "handwriting" and card.material and "handwriting" not in card.material:
        return "no-reader-for-material", "it is made for print or typescript, never handwriting"
    if not card.open_licence:
        return "licence-not-accepted", "its licence is not open (accept it to use it)"
    if not card.local and card.runs_on.startswith("cloud:") and not a.cloud_allowed:
        return "cloud-not-allowed", "it runs in the cloud and this project keeps pages on this Mac"
    if card.local and card.memory_gb > a.mac_memory_gb - MEMORY_HEADROOM_GB:
        return "not-enough-memory", "this Mac does not have the memory to run it alongside macOS and Fichero"
    return None


def _hard_constraints(job: str, card: Card, a: Answers, material: str | None = None) -> str | None:
    """Why `card` cannot do `job` for this project, or None if it may."""
    refused = _refusal(job, card, a, material or a.material)
    return refused[1] if refused else None


_NOUNS = {"read-a-line": "reading model", "read-a-page": "reading model", "correct": "correcting model",
          "find-lines": "line finder", "find-names-tag-words": "name finder", "make-a-vector": "search model",
          "translate-transliterate-normalise": "translating model"}
#: Each refusal's fixes, the first the one setup offers as its button (`source.onboard.says-no-model`).
_FIXES = {
    "no-model-for-job": ["choose-model"],
    "no-model-for-script": ["download", "choose-cloud", "choose-model"],
    "no-model-for-language": ["download", "choose-cloud", "choose-model"],
    "no-reader-for-material": ["download", "choose-model"],
    "licence-not-accepted": ["accept-licence", "choose-model"],
    "cloud-not-allowed": ["allow-cloud", "choose-model"],
    "not-enough-memory": ["choose-cloud", "choose-model"],
}


def _and(names: list[str]) -> str:
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def _sentence(code: str, job: str, a: Answers, material: str) -> str:
    """One sentence a historian reads, built from the rule that refused: names of languages and
    scripts, never a model's id, pin or repository (`source.onboard.never-raw-model-ids`)."""
    from fichero_server.recipes.jobs import get_job
    from fichero_server.recipes.names import language_name, script_name

    known = get_job(job)
    noun = _NOUNS.get(job) or f"model for “{known.name if known else job}”"
    if code == "no-model-for-job":
        return f"Fichero has no {noun} yet."
    if code == "no-model-for-script":
        return f"No {noun} here reads {_and([script_name(s) for s in sorted(a.scripts)])} yet."
    if code == "no-model-for-language":
        return f"No {noun} here knows {_and([language_name(t) for t in sorted(a.languages)])} yet."
    if code == "no-reader-for-material":
        return f"No {noun} here is made for {material}."
    if code == "licence-not-accepted":
        return f"The {noun} that fits has a licence you have not accepted yet."
    if code == "cloud-not-allowed":
        return f"Only a cloud {noun} fits, and this project keeps its pages on this Mac."
    return f"The {noun} that fits needs more memory than this Mac has."


def _problem(job: str, cards: list[Card], a: Answers, material: str, detail: str) -> dict[str, Any]:
    """The step's one problem (`source.onboard.says-no-model`): the refusal of the card that got
    furthest through the rules, as a code, a sentence and its fixes; the rules' own reason in `detail`."""
    codes = [r[0] for c in cards if (r := _refusal(job, c, a, material)) is not None]
    code = max(codes, key=_CONSTRAINTS.index, default="no-model-for-job")
    fixes = list(_FIXES[code])
    # `kind`, not `code`: a recipe refuses any key named code (`recipe._FORBIDDEN_KEYS`), and this one is saved.
    return {"kind": code, "sentence": _sentence(code, job, a, material), "fix": fixes[0], "fixes": fixes,
            "detail": detail}


def _accuracy(card: Card) -> float:
    cer = card.cer_measured_here if card.cer_measured_here is not None else card.cer_published
    return cer if cer is not None else 1.0


def _rank_key(card: Card, material: str) -> tuple:
    """The fixed order (section 8): accuracy in one-point bands, then local before remote, cheaper,
    faster, lower carbon, trainable, smaller, and the card id so ties are deterministic. The
    material soft rule ranks a reader made for the material first."""
    band = int(_accuracy(card) * 100)
    return (
        band,
        0 if material in card.material else 1,
        0 if card.local else 1,
        card.cost_per_page,
        -card.pages_per_hour,
        card.carbon_g_per_page if card.carbon_g_per_page is not None else float("inf"),
        0 if card.trainable else 1,
        card.size_gb,
        card.id,
    )


def _choose(job: str, cards: list[Card], a: Answers, material: str | None = None) -> Choice:
    material = material or a.material
    kept = [c for c in cards if _refusal(job, c, a, material) is None]
    if not kept:
        named = [c for c in cards if job in c.jobs]
        why = "; ".join(sorted({f"{c.id}: {_hard_constraints(job, c, a, material)}" for c in named})) \
            or "no card names this job"
        gap = f"no model fits this step ({why})"
        return Choice(job, None, gap=gap, problem=_problem(job, cards, a, material, gap))
    # Cheapest and local first: start with the best LOCAL candidate; a remote one only when no
    # local one passes (the A/B, not the rules, decides any move to a costlier option).
    pool = [c for c in kept if c.local] or kept
    if job == "make-a-vector":
        # The embedder: the smallest local model whose card covers all the project's languages.
        pool = sorted(pool, key=lambda c: (c.size_gb, c.id))[:1]
    best = sorted(pool, key=lambda c: _rank_key(c, material))[0]
    reasons = [f"its card names this job; covers {', '.join(sorted(a.scripts))}"]
    if best.languages is not None and job in LANGUAGE_JOBS:
        reasons.append(f"lists {', '.join(sorted(a.languages))}")
    if material in best.material:
        reasons.append(f"made for {material}")
    acc = best.cer_measured_here if best.cer_measured_here is not None else best.cer_published
    if acc is not None:
        where = "on your pages" if best.cer_measured_here is not None else "as published"
        reasons.append(f"CER {acc * 100:.1f}% {where}")
    if best.cer_measured_here is None:
        reasons.append("unmeasured on your pages until a bake-off measures it")
    if best.offered_because:
        reasons.append(best.offered_because)
    reasons.append("runs on this Mac, free" if best.local else f"runs on {best.runs_on}")
    if best.trainable:
        reasons.append("trainable on your corrections")
    return Choice(job, best, reasons=reasons)


def _chosen(choice: Choice) -> dict[str, Any]:
    """A choice as recipe data: the model, where it runs, why, and its card's facts; or its gap and problem."""
    if choice.card is None:
        return {"gap": choice.gap, "problem": choice.problem}
    card = choice.card
    return {
        "model": dict(card.pin), "runs_on": card.runs_on, "reasons": choice.reasons,
        "card": {
            "id": card.id, "note": card.note, "licence": card.licence,
            "open_licence": card.open_licence, "size_gb": card.size_gb,
            "memory_gb": card.memory_gb, "cer_measured_here": card.cer_measured_here,
            "cer_published": card.cer_published, "trainable": card.trainable, "source": card.source,
        },
    }


def _topic(job: str) -> dict[str, Any]:
    """The step's topic (the registry's explanation, written once): its id, title and one sentence."""
    from fichero_server.recipes.jobs import get_job

    known = get_job(job)
    topic = known.topic if known else None
    return {"topic": topic.id, "title": topic.title, "sentence": topic.short} if topic else {}


def assemble(a: Answers, cards: list[Card]) -> dict[str, Any]:
    """The recipe for these answers, as recipe.yaml data, with each step's reasons and any gaps."""
    jobs = set(purpose_jobs(a.purposes))
    jobs |= {j for layer in a.layers for j in layer_jobs(layer)}
    jobs |= {j for j in a.jobs if j in STEP_ORDER}
    train_ticked = "train-a-model" in jobs
    jobs.discard("train-a-model")
    jobs_in_order = sorted(jobs, key=STEP_ORDER.index)
    if (train_ticked or a.pages >= TRAIN_OFFERED_FROM_PAGES) and jobs_in_order:
        # Training sits after what it learns from and before the checks and output.
        tail = [j for j in jobs_in_order if STEP_ORDER.index(j) > STEP_ORDER.index("train-a-model")]
        jobs_in_order = [j for j in jobs_in_order if j not in tail] + ["train-a-model"] + tail
    steps, notes = [], []
    for job in jobs_in_order:
        if job == "train-a-model":
            why = (f"{a.pages} pages: a reader trained on your corrections repays its training"
                   if a.pages >= TRAIN_OFFERED_FROM_PAGES else "you ticked it")
            steps.append({"id": job, "job": job, "layer": "train", **_topic(job),
                          "offered_when": {"corrected_lines_at_least": 2000},
                          "settings": {"base": "read-a-line"}, "runs_on": "cluster", "reasons": [why]})
            continue
        choice = _choose(job, cards, a)
        step: dict[str, Any] = {"id": job, "job": job, **_topic(job)}
        if len(a.materials) > 1 and job in READING_JOBS:
            # One reader per kind of material ticked; the step's own model is the default kind's,
            # until a folder or page override says which applies where (`source.onboard.material-any-mix`).
            step["material"] = a.material
            step["readers"] = [{"material": m, **_chosen(_choose(job, cards, a, m))} for m in a.materials]
        step.update(_chosen(choice))
        if choice.card is None:
            notes.append(f"{job}: {choice.gap}")
        step["uses_cloud"] = str(step.get("runs_on") or "").startswith("cloud")
        steps.append(step)
    # Where a cloud model would also fit if pages could leave this Mac: setup asks the egress
    # question only when this is not empty (`source.onboard.cloud-asked-once`).
    with_cloud = Answers(**{**a.__dict__, "cloud_allowed": True})
    cloud_options = sorted({
        job for job in jobs_in_order for c in cards
        if job in c.jobs and c.runs_on.startswith("cloud") and _hard_constraints(job, c, with_cloud) is None
    })
    named = "+".join(a.purposes) or "not-sure"
    return {
        "fichero_recipe": 1,
        "id": f"generated/{named}-{'-'.join(sorted(a.languages))}-{'-'.join(sorted(a.scripts))}",
        "version": "0.1.0",
        "title": f"Generated for {', '.join(a.purposes) or 'not-sure'}: "
                 f"{', '.join(sorted(a.languages))} in {', '.join(sorted(a.scripts))}",
        "suits": {"scripts": sorted(a.scripts), "languages": sorted(a.languages), "material": list(a.materials)},
        "purposes": list(a.purposes),
        "steps": steps,
        "gaps": notes,
        "cloud_options": cloud_options,
    }
