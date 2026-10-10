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

from fichero_server.finddocs import AUTO_ACCEPT_ABOVE

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

#: How setup offers each purpose: its label and one sentence, in the order setup lists them. One list, read
#: by setup, the Inspector and the manual (`source.onboard.purpose-first`). The order and grouping were ruled
#: by the maintainer 2026-10-09 (#5625, `source.onboard.purposes-grouped`): Transcribe, with Search under it;
#: Translate after; the Knowledge graph with Entities and Statements as its options below it.
PURPOSES: dict[str, tuple[str, str]] = {
    "transcribe": ("Transcribe", "Read every page into text you can correct."),
    "search": ("Search", "Make the text searchable by meaning, not only by its words."),
    "translate-normalise": ("Translate or normalise",
                            "Transcribe, then translate, transliterate or normalise the spelling."),
    "knowledge-graph": ("Knowledge graph",
                        "Everything below, with dates and links to authorities, joined into one graph you can "
                        "question and search."),
    "entities": ("Entities", "Find the people, places and things named in the text."),
    "statements": ("Statements", "Find who did what to whom, each tied to its line."),
    "map-places": ("Map places", "Find the places in the text and put them on a map."),
    "quotations": ("Gather quotations", "Transcribe, then pull out the passages you are looking for."),
    "catalogue": ("Catalogue my sources", "Transcribe, then describe each source for the catalogue."),
    "tables": ("Tables and forms", "Find each table's cells, read them, and gather the rows into a table."),
    "edit-corpus": ("Edit a corpus", "Lines and readings to edit by hand; nothing runs by itself after."),
    "decipher": ("Decipher a script", "Tools for signs not yet read; nothing runs by itself."),
    "not-sure": ("Not sure yet", "Import first; the tools are offered when you want them."),
}
assert set(PURPOSES) == set(PURPOSE_STEPS)
#: A purpose shown as an option under another (#5625): still a purpose of its own, ticked on its own, but listed
#: indented below its parent. Where the parent's jobs hold all of the option's, ticking the parent includes it.
PURPOSE_PARENT: dict[str, str] = {"search": "transcribe", "entities": "knowledge-graph",
                                  "statements": "knowledge-graph"}
assert all(c in PURPOSES and p in PURPOSES and list(PURPOSES).index(p) < list(PURPOSES).index(c)
           for c, p in PURPOSE_PARENT.items())
#: Purposes that offer tools rather than running by themselves after Start (section 7b, screen 7).
TOOL_PURPOSES = frozenset({"edit-corpus", "decipher", "not-sure"})
#: The kinds of material setup offers as checkboxes, in the order the default reader is taken from.
#: "text" is material that is already text (Markdown, plain text, Word, a PDF with a text layer, notes from a
#: note-taking app): nothing reads it (`source.recipe.text-material-is-not-read`, #5553).
MATERIALS: tuple[str, ...] = ("handwriting", "print", "typescript", "text")
#: The materials a reader reads (a reading step gets one reader per kind ticked).
READ_MATERIALS: tuple[str, ...] = tuple(m for m in MATERIALS if m != "text")
#: The jobs that make a page's text from its picture: a project whose material is all text runs none of them, and
#: its plan starts at what was ticked after reading (search, names, ...) (#5553).
READING_THE_PICTURE = frozenset({"split-pages", "prepare-the-image", "find-regions", "find-lines", "put-in-order",
                                 "refine-shapes", "find-signs", "find-a-tables-cells", "read-a-line", "read-a-page",
                                 "tie-text-to-lines", "correct", "train-a-model"})
#: Jobs that read the material: they get one reader per kind of material ticked.
READING_JOBS = frozenset({"read-a-line", "read-a-page"})
#: Finding the documents in a box of loose pages, after reading (`finddocs.recipe-step`, #5550).
FIND_DOCUMENTS = "find-documents-in-a-folder"
#: Preparing faded pages (their contrast raised on a new rendition) before lines, where the sample shows them
#: (`source.onboard.auto.prepare-damaged-images`, #5580).
PREPARE = "prepare-the-image"
#: Steps Fichero carries out itself, with no model to choose (`source.recipe.fichero-does-it-steps`, #5619): the
#: built-in each runs and why, in words. The Start plan runs them as their shipped workflows (`start.py`).
FICHERO_DOES_IT: dict[str, tuple[dict[str, str], tuple[str, ...]]] = {
    "split-pages": ({"builtin": "page-splitter"},
                    ("Fichero's page splitter: finds the document in each photograph with Apple Vision and cuts an "
                     "open spread at its gutter, on this Mac, free",
                     "a closed notebook or a single page is kept whole; an unclear gutter is proposed, never cut")),
    "work-out-dates": ({"builtin": "date-rules"},
                       ("Fichero's date rules read the dates the names step found, on this Mac, free",)),
}

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
    "split-pages", "prepare-the-image", "find-regions", "find-lines",
    "put-in-order", "refine-shapes", "find-signs", "find-a-tables-cells", "read-a-line", "read-a-page",
    "tie-text-to-lines", "transcribe-speech", "correct", "find-documents-in-a-folder", "trace-a-drawing",
    "identify-signs",
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
    """The jobs a layer turns on, in order: the assembled jobs whose registry entry names that layer, and that
    Start can run (#5574)."""
    from fichero_server.recipes.jobs import get_job
    from fichero_server.recipes.start import start_runs

    return tuple(j for j in LAYER_STEPS if (job := get_job(j)) is not None and job.layer == layer and start_runs(j))


def addable_layers() -> list[str]:
    """The layers a project can add later: those the rules can assemble a step for that Start can run."""
    from fichero_server.recipes.jobs import get_job
    from fichero_server.recipes.start import start_runs

    return list(dict.fromkeys(get_job(j).layer for j in LAYER_STEPS if start_runs(j)))


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
    #: Whether its model is already on this Mac (#5583): True or False for a model a person downloads before
    #: Start (an MLX model in this Mac's store), None where that does not apply (a Kraken reader the run fetches,
    #: a built-in, a cloud model). A model already here wins over one to download (`_rank_key`).
    installed: bool | None = None

    def __post_init__(self) -> None:
        # A card that lists a language also covers the languages written as it (a Syriac reader reads Classical
        # Syriac): one place, so every rule that compares languages agrees (#5595).
        if self.languages is not None:
            from fichero_server.recipes.names import languages_covered

            object.__setattr__(self, "languages", languages_covered(self.languages))

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
    #: Steps the person took out of the plan on Ready (#5627, `source.onboard.plan-editable`), by job: never
    #: proposed again while they stay out, unless a step left in needs what one gives (then it stays, saying so).
    removed_jobs: tuple[str, ...] = ()
    #: The material is loose pages (a box or bundle not yet sorted into documents): a recipe that reads them
    #: then finds the documents among them (`finddocs.recipe-step`, #5550).
    loose_pages: bool = False
    #: The project's sample shows faded pages (`recipes/prepare.sample_shows_faded`): a recipe that lines or reads
    #: them prepares them first (#5580).
    faded_pages: bool = False
    #: The answers under a purpose (`answers.job_answers`): which kinds of names, which gazetteer, how far to
    #: normalise; each reaches the setting of the step it configures (`start.JOB_ANSWER_SETTINGS`, #5478).
    job_answers: dict[str, Any] = field(default_factory=dict, compare=False, hash=False)
    #: The model this engine's search embeds with (its one embedding space); the search step names it where its
    #: card fits (#5574). Empty: no preference.
    search_embedder: str = ""

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


#: How many nearest readers a "nothing fits" problem names (`source.onboard.nothing-fits-names-nearest`).
NEAREST = 3
#: A script's parent: the script a variant of it is filed under (Fraktur and Gaelic are Latin; Simplified and
#: Traditional Han are Han; the Syriac and Arabic styles their script). ISO 15924 data, not a model's name.
_PARENT = {"Latf": "Latn", "Latg": "Latn", "Hans": "Hani", "Hant": "Hani", "Syre": "Syrc", "Syrj": "Syrc",
           "Syrn": "Syrc", "Aran": "Arab", "Cyrs": "Cyrl"}
#: A script's parts, where ISO 15924 names a whole made of others (Japanese is Han plus the kana).
_PARTS = {"Jpan": frozenset({"Hani", "Hira", "Kana", "Hrkt"}), "Kore": frozenset({"Hang", "Hani"}),
          "Hrkt": frozenset({"Hira", "Kana"})}


def _family(code: str) -> str:
    """The script a code belongs to for "a related script": its parent, else itself."""
    return _PARENT.get(code, code)


def _related_scripts(scripts: frozenset[str]) -> frozenset[str]:
    """The asked scripts with their parents and their parts: what a reader made for them may also state."""
    out = set(scripts) | {_PARENT[s] for s in scripts if s in _PARENT}
    for s in scripts:
        out |= _PARTS.get(s, frozenset())
    return frozenset(out)


def made_for_script(card: Card, a: Answers | None) -> bool:
    """Whether `card` is a reader made for the project's script (`source.recipe.script-reader-first`): it states
    scripts, each the asked one, its parent or one of its parts; it lists the project's languages; and it states
    a published CER. A card trained on many scripts is generic however low its own CER."""
    if a is None or not a.scripts or card.scripts is None or card.cer_published is None:
        return False
    if a.languages and (card.languages is None or not a.languages <= card.languages):
        return False
    return card.scripts <= _related_scripts(a.scripts)


def _name(card: Card) -> str:
    """A card as a person reads it: its note's first clause, short; never its id."""
    words = (card.note or "").strip().split(". ")[0].strip().rstrip(".")
    return words if len(words) <= 60 else words[:57].rstrip() + "…"


def _nearest(job: str, cards: list[Card], a: Answers, material: str) -> list[dict[str, str]]:
    """Up to `NEAREST` refused readers closest to fitting, in words (`source.onboard.nothing-fits-names-nearest`):
    one for the asked script refused for another reason (another material, memory, licence, the cloud), then one
    for a related script (Han for Traditional Han), then one listing the project's language."""
    from fichero_server.recipes.names import language_name, script_name

    families = {_family(s) for s in _related_scripts(a.scripts)}
    ranked: list[tuple[int, tuple, Card, str]] = []
    for card in cards:
        if job not in card.jobs or not card.note or card.scripts is None:
            continue
        refused = _refusal(job, card, a, material)
        if refused is None:
            continue
        if refused[0] != "no-model-for-script":
            why, tier = refused[1], 0
        elif {_family(s) for s in card.scripts} & families:
            # Named by the scripts it states, a whole (Japanese) rather than its parts (Han, kana).
            parts = {p for s in card.scripts for p in _PARTS.get(s, ())}
            shown = sorted(card.scripts - parts)[:2]
            # "Japanese", not "Japanese (alias for Han + Hiragana + Katakana)".
            why, tier = f"reads {_and([script_name(s).split(' (')[0] for s in shown])}, a related script", 1
        elif a.languages and card.languages and a.languages & card.languages:
            why, tier = (f"lists {_and([language_name(t) for t in sorted(a.languages & card.languages)])}, "
                         "in another script"), 2
        else:
            continue
        ranked.append((tier, _rank_key(card, material, a), card, why))
    ranked.sort(key=lambda r: (r[0], r[1]))
    seen: set[str] = set()
    out = []
    for _, _, card, why in ranked:
        if _name(card) in seen:
            continue
        seen.add(_name(card))
        out.append({"card": card.id, "name": _name(card), "why": why})
        if len(out) == NEAREST:
            break
    return out


def _problem(job: str, cards: list[Card], a: Answers, material: str, detail: str) -> dict[str, Any]:
    """The step's one problem (`source.onboard.says-no-model`): the refusal of the card that got
    furthest through the rules, as a code, a short sentence naming the nearest readers, and its fixes; the rules'
    own reason, short, in `detail`, and every refused card in `refused` (`source.onboard.nothing-fits-names-nearest`)."""
    refusals = [(c, r) for c in cards if job in c.jobs and (r := _refusal(job, c, a, material)) is not None]
    codes = [r[0] for c in cards if (r := _refusal(job, c, a, material)) is not None]
    code = max(codes, key=_CONSTRAINTS.index, default="no-model-for-job")
    fixes = list(_FIXES[code])
    nearest = _nearest(job, cards, a, material)
    sentence = _sentence(code, job, a, material)
    if nearest:
        sentence += " Nearest: " + "; ".join(f"{n['name']} ({n['why']})" for n in nearest) + "."
    # `kind`, not `code`: a recipe refuses any key named code (`recipe._FORBIDDEN_KEYS`), and this one is saved.
    return {"kind": code, "sentence": sentence, "fix": fixes[0], "fixes": fixes, "detail": detail,
            "nearest": nearest,
            "refused": [{"card": c.id, "why": r[1]} for c, r in sorted(refusals, key=lambda cr: cr[0].id)]}


def _material_rank(card: Card, material: str) -> int:
    """0: its card states the material; 1: it states none; 2: it states another."""
    return 0 if material in card.material else 1 if not card.material else 2


def _rank_key(card: Card, material: str, a: Answers | None = None) -> tuple:
    """The fixed order (section 8, `source.recipe.script-reader-first`): a measurement on the project's pages in
    one-point bands first; then a reader made for the project's script before a generic one; then one whose card
    states the material, then one that states none; then the published CER in one-point bands, so a published
    CER only ranks cards of the same script tier and material; then a model already on this Mac before one to
    download (`source.onboard.auto.installed-model-first`, #5583), local before remote, cheaper, faster, lower
    carbon, trainable, smaller, and the card id so ties are deterministic. Without answers (the bake-off's own
    rows) every card is one tier."""
    measured = int(card.cer_measured_here * 100) if card.cer_measured_here is not None else 100
    band = int((card.cer_published if card.cer_published is not None else 1.0) * 100)
    return (
        measured,
        0 if made_for_script(card, a) else 1,
        _material_rank(card, material),
        band,
        1 if card.installed is False else 0,
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
        # Short: how many cards were refused, by reason, naming the first few; each card and why is the problem's
        # `refused` list (`source.onboard.nothing-fits-names-nearest`: the detail was a 4 KB dump of ~45 ids).
        by_reason: dict[str, list[str]] = {}
        for c in sorted(cards, key=lambda c: c.id):
            if job in c.jobs:
                by_reason.setdefault(str(_hard_constraints(job, c, a, material)), []).append(c.id)

        def said(reason: str, ids: list[str]) -> str:
            more = f", and {len(ids) - 2} more" if len(ids) > 2 else ""
            return f"{len(ids)} {'card' if len(ids) == 1 else 'cards'}: {reason} ({', '.join(ids[:2])}{more})"

        why = "; ".join(said(reason, ids) for reason, ids in sorted(by_reason.items())) or "no card names this job"
        gap = f"no model fits this step ({why})"
        return Choice(job, None, gap=gap, problem=_problem(job, cards, a, material, gap))
    # Cheapest and local first: start with the best LOCAL candidate; a remote one only when no
    # local one passes (the A/B, not the rules, decides any move to a costlier option).
    pool = [c for c in kept if c.local] or kept
    if job == "make-a-vector":
        # The embedder: the one this engine's search embeds with, where its card covers all the project's
        # languages (vectors from another could not be searched beside them, #5574); else the smallest local one.
        engine = a.search_embedder.lower()
        pool = sorted(pool, key=lambda c: (not engine or str(c.pin.get("hf", "")).lower() != engine,
                                           c.size_gb, c.id))[:1]
    best = sorted(pool, key=lambda c: _rank_key(c, material, a))[0]
    reasons = [f"its card names this job; covers {', '.join(sorted(a.scripts))}"]
    if made_for_script(best, a):
        reasons.append(f"made for {', '.join(sorted(a.scripts))}")
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
    if best.installed:
        reasons.append("already on this Mac")
    elif best.installed is False:
        reasons.append(f"to download first ({best.size_gb:g} GB)" if best.size_gb
                       else "to download first (its size is not stated)")
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


def needed_by(job: str, jobs_in_order: list[str], materials=()) -> list[str]:
    """The later steps that would lose an input if `job` were taken out of this plan: each needs a kind of thing
    only `job` gives before it (`jobs.unmet_inputs`, the recipe check's own rule). [] when it can go."""
    from fichero_server.recipes.jobs import get_job, starts_with

    def unmet(order: list[str]) -> set[str]:
        have, out = set(starts_with(materials)), set()
        for j in order:
            known = get_job(j)
            if known is None:
                continue
            if any(have.isdisjoint(kind.split("|")) for kind in known.takes):
                out.add(j)
            have |= known.gives
        return out

    lost = unmet([j for j in jobs_in_order if j != job]) - unmet(jobs_in_order)
    return [j for j in jobs_in_order if j in lost]


def _take_out(jobs_in_order: list[str], a: Answers) -> tuple[list[str], list[dict[str, str]]]:
    """The plan without the steps the person took out (#5627), in step order. A step a step left in needs stays
    (it carries `needed_by`); a removed job the plan no longer has is ignored. Returns the plan and what was taken
    out, each with its title, so Ready can offer to put it back."""
    from fichero_server.recipes.jobs import get_job

    taken_out = []
    for job in sorted(set(a.removed_jobs) & set(jobs_in_order), key=STEP_ORDER.index, reverse=True):
        # Latest first: taking out a step and the one that needed it, together, frees the earlier one too.
        if not needed_by(job, jobs_in_order, a.materials):
            jobs_in_order = [j for j in jobs_in_order if j != job]
            known = get_job(job)
            taken_out.append({"job": job, "title": known.name if known else job})
    return jobs_in_order, sorted(taken_out, key=lambda t: STEP_ORDER.index(t["job"]))


def assemble(a: Answers, cards: list[Card]) -> dict[str, Any]:
    """The recipe for these answers, as recipe.yaml data, with each step's reasons and any gaps. A job Start
    cannot run by itself is never a step: it is listed under `by_hand`, with why and the tool that does it by hand
    (`source.onboard.auto.every-proposed-step-runs`, #5574)."""
    from fichero_server.recipes.start import JOB_ANSWER_SETTINGS, by_hand, start_runs

    jobs = set(purpose_jobs(a.purposes))
    jobs |= {j for layer in a.layers for j in layer_jobs(layer)}
    jobs |= {j for j in a.jobs if j in STEP_ORDER}
    already_text = set(a.materials) == {"text"}
    if already_text:
        # Nothing to read: the plan starts at what comes after reading (#5553).
        jobs -= READING_THE_PICTURE
    if a.loose_pages and jobs & READING_JOBS:
        jobs.add(FIND_DOCUMENTS)
    if a.faded_pages and jobs & (READING_JOBS | {"find-lines"}):
        jobs.add(PREPARE)
    left_by_hand = [by_hand(j) for j in sorted(jobs, key=STEP_ORDER.index) if not start_runs(j)]
    jobs = {j for j in jobs if start_runs(j)}
    train_ticked = "train-a-model" in jobs
    jobs.discard("train-a-model")
    jobs_in_order = sorted(jobs, key=STEP_ORDER.index)
    if (train_ticked or a.pages >= TRAIN_OFFERED_FROM_PAGES) and jobs_in_order and not already_text:
        # Training sits after what it learns from and before the checks and output.
        tail = [j for j in jobs_in_order if STEP_ORDER.index(j) > STEP_ORDER.index("train-a-model")]
        jobs_in_order = [j for j in jobs_in_order if j not in tail] + ["train-a-model"] + tail
    jobs_in_order, taken_out = _take_out(jobs_in_order, a)
    needs = {job: needed_by(job, jobs_in_order, a.materials) for job in jobs_in_order}
    steps, notes = [], []
    for job in jobs_in_order:
        if job == "train-a-model":
            why = (f"{a.pages} pages: a reader trained on your corrections repays its training"
                   if a.pages >= TRAIN_OFFERED_FROM_PAGES else "you ticked it")
            steps.append({"id": job, "job": job, "layer": "train", **_topic(job),
                          "offered_when": {"corrected_lines_at_least": 2000},
                          "settings": {"base": "read-a-line"}, "runs_on": "cluster", "reasons": [why]})
            continue
        if job == FIND_DOCUMENTS:
            # Fichero's own rules, no model to choose: every project can run it (`finddocs.recipe-step`).
            steps.append({"id": job, "job": job, **_topic(job), "model": {"builtin": "document-finder"},
                          "runs_on": "this-mac", "uses_cloud": False,
                          "settings": {"accept_above": AUTO_ACCEPT_ABOVE},
                          "reasons": ["reads the text already there and the pages' thumbnails, on this Mac, free",
                                      "proposes the documents for you to accept" if AUTO_ACCEPT_ABOVE is None
                                      else f"proposes; accepts by itself only a document's pages at least "
                                           f"{AUTO_ACCEPT_ABOVE:.0%} sure (one undo restores)"]})
            continue
        if job in FICHERO_DOES_IT:
            # Fichero carries it out itself: no model to choose, so never "Fichero has no model" (#5619).
            pin, why = FICHERO_DOES_IT[job]
            steps.append({"id": job, "job": job, **_topic(job), "model": dict(pin), "runs_on": "this-mac",
                          "uses_cloud": False, "reasons": list(why)})
            continue
        if job == PREPARE:
            # Fichero's own measure and contrast, no model to choose (`recipes/prepare.py`).
            why = ("the sample pages show faded ink" if a.faded_pages else "you ticked it")
            steps.append({"id": job, "job": job, **_topic(job), "model": {"builtin": "image-preparer"},
                          "runs_on": "this-mac", "uses_cloud": False,
                          "reasons": [why, "raises the contrast of each faded page on a new copy, on this Mac, free, "
                                           "before lines; the original is kept"]})
            continue
        choice = _choose(job, cards, a)
        step: dict[str, Any] = {"id": job, "job": job, **_topic(job)}
        read = [m for m in a.materials if m in READ_MATERIALS]  # material already text has no reader (#5553)
        if len(read) > 1 and job in READING_JOBS:
            # One reader per kind of material ticked; the step's own model is the default kind's,
            # until a folder or page override says which applies where (`source.onboard.material-any-mix`).
            step["material"] = a.material
            step["readers"] = [{"material": m, **_chosen(_choose(job, cards, a, m))} for m in read]
        step.update(_chosen(choice))
        answer, setting = JOB_ANSWER_SETTINGS.get(job, (None, None))
        if answer and a.job_answers.get(answer) not in (None, "", []):
            step["settings"] = {setting: a.job_answers[answer]}
        if choice.card is None:
            notes.append(f"{job}: {choice.gap}")
        step["uses_cloud"] = str(step.get("runs_on") or "").startswith("cloud")
        steps.append(step)
    for step in steps:
        if needs.get(step["job"]):
            # Ready offers no Remove for a step a later one needs, and says which (#5627).
            step["needed_by"] = needs[step["job"]]
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
        "by_hand": left_by_hand,
        "removed": taken_out,
        "gaps": notes,
        "cloud_options": cloud_options,
        # What Ready says when there is nothing to read (#5553).
        **({"already_text": "The material is already text: nothing to read"
                            + (f"; the plan starts at {_topic(jobs_in_order[0]).get('title', jobs_in_order[0])}."
                               if jobs_in_order else ".")} if already_text else {}),
    }
