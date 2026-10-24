"""The job registry: what each job takes, what it gives, and how it explains itself.

`source/models-chains-and-projects.md` section 2 (`source.recipe.jobs-are-a-registry`,
`source.recipe.steps-are-jobs`). A recipe is written in jobs, not tools: each step names a job, and
because every job declares the KINDS of thing it takes and gives, a recipe can be checked before it
runs (a step may only use what an earlier step produced). The registry is open: a feature adds a
job by calling `register_job`, and recipes, onboarding, the activity queue and the recipe check
pick it up with no other change. Each job's name and description are its entry in the topic
registry (`recipes/seed/topics.yaml`, #5471): the plain text setup, the Inspector, Activity, the
recipe README and the user manual show, written once (`source.onboard.topics-written-once`).

A job is not a tool: the workflow tools (`workflows/registry.py`) are how a job is carried out;
a job is what a recipe asks for.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from fichero_server.recipes.topics import Topic, get_topic

# The kinds of thing that flow between jobs. A page image is what every project starts with.
STARTS_WITH = frozenset({"page_image"})
#: Material that is already text (born-digital notes, a PDF with a text layer) starts with the page's text as
#: well, so its recipe needs no reading step (`source.recipe.text-material-is-not-read`, #5553).
TEXT_STARTS_WITH = STARTS_WITH | {"page_reading"}
#: A `takes` entry may name kinds joined by "|": any one of them meets it (`source.chain.checked-before-run`).
READING = "line_readings|page_reading"


@dataclass(frozen=True)
class Job:
    """One registered job."""

    id: str
    takes: frozenset[str]
    gives: frozenset[str]
    layer: str
    #: How two runs of this job are compared in an A/B (section 8a).
    compare: str
    #: The Fichero version that added it, so a recipe naming a job this copy lacks can say which has it.
    since: str = "2026.10.03"
    settings: tuple[str, ...] = field(default_factory=tuple)
    #: The topic registry entry that explains it; the job's own id unless named.
    topic_id: str = ""
    #: Whether the step needs a model of its own, yes or no (`source.recipe.every-job-declares-needs-a-model`, #5812).
    #: Required: None is refused at registration. A "no" job gets no model row, no finder and no "has no model" skip.
    needs_a_model: bool | None = None

    @property
    def topic(self) -> Topic | None:
        return get_topic(self.topic_id or self.id)

    @property
    def name(self) -> str:
        return self.topic.title if self.topic else self.id

    @property
    def description(self) -> str:
        """What it does and why a recipe includes it, in a researcher's words (its topic's text)."""
        return self.topic.text if self.topic else ""


_JOBS: dict[str, Job] = {}


def register_job(job: Job) -> Job:
    """Add a job. A second registration of one id is a mistake, not an update."""
    if job.id in _JOBS:
        raise ValueError(f"job {job.id!r} is already registered")
    if job.needs_a_model is None:
        raise ValueError(f"job {job.id!r} does not say whether it needs a model: declare needs_a_model=True or False")
    if job.topic is None or job.topic.kind != "job":
        raise ValueError(f"job {job.id!r} has no entry in the topic registry: setup and the manual show it")
    _JOBS[job.id] = job
    return job


def get_job(job_id: str) -> Job | None:
    return _JOBS.get(job_id)


def all_jobs() -> list[Job]:
    return list(_JOBS.values())


def _job(id, takes, gives, layer, compare, settings=(), *, needs_a_model):  # noqa: A002
    return register_job(Job(id, frozenset(takes), frozenset(gives), layer, compare,
                            settings=tuple(settings), needs_a_model=needs_a_model))


_TEXT = "a text diff of the readings, with character and word error rates where pages are corrected"
_BOXES = "the shapes side by side, with precision and recall against shapes a person has checked"
_LIST = "the two lists side by side, with precision and recall where a person has confirmed some"

# --- Reading jobs ---------------------------------------------------------------------------------
_job("prepare-the-image", {"page_image"}, {"page_image", "rendition"}, "prepare", "the renditions side by side",
     ("operations",), needs_a_model=False)
_job("split-pages", {"page_image"}, {"page_image"}, "prepare", "the cut pages side by side", needs_a_model=False)
_job("find-the-script", {"page_image"}, {"script"}, "prepare", "the scripts found, side by side", ("model",), needs_a_model=True)
_job("find-regions", {"page_image"}, {"regions"}, "lines", _BOXES, ("model",), needs_a_model=True)
_job("find-lines", {"page_image"}, {"lines"}, "lines", _BOXES, ("model", "regions"), needs_a_model=True)
# Marks the lines that are not writing (too small, off the page, bleed-through) LEFT OUT before Read; never deletes (#6070).
_job("leave-out", {"lines"}, {"lines"}, "lines", _BOXES, needs_a_model=False)
_job("put-in-order", {"lines"}, {"reading_order"}, "lines", "the two orders side by side", needs_a_model=False)
_job("refine-shapes", {"page_image", "lines"}, {"lines"}, "lines", _BOXES, ("model",), needs_a_model=True)
_job("find-signs", {"page_image"}, {"signs"}, "lines", _BOXES, ("model",), needs_a_model=True)
_job("find-a-tables-cells", {"regions"}, {"table_cells"}, "lines", _BOXES, ("model",), needs_a_model=True)
_job("read-a-line", {"lines"}, {"line_readings"}, "reading", _TEXT, ("model", "prompt"), needs_a_model=True)
_job("read-a-page", {"page_image"}, {"page_reading"}, "reading", _TEXT, ("model", "prompt"), needs_a_model=True)
_job("tie-text-to-lines", {"page_reading", "lines"}, {"line_readings"}, "reading", _TEXT, needs_a_model=False)
_job("correct", {"line_readings"}, {"line_readings"}, "reading", _TEXT, ("model", "prompt", "only_below_confidence"), needs_a_model=True)
# Each line read by several readers, or one sampled N times at a temperature; every reading kept (#5665).
_job("find-where-readers-disagree", {"lines"}, {"line_readings"}, "reading", _TEXT,
     ("model", "readers", "samples", "temperature"), needs_a_model=False)
_job("trace-a-drawing", {"regions"}, {"drawings"}, "reading", "the drawings side by side", ("model",), needs_a_model=True)
_job("identify-signs", {"signs"}, {"sign_identifications"}, "reading", _LIST, ("model",), needs_a_model=True)
_job("transcribe-speech", {"recording"}, {"line_readings"}, "reading", _TEXT, ("model",), needs_a_model=True)
_job("translate-transliterate-normalise", {"line_readings"}, {"line_readings"}, "reading", _TEXT, ("model", "target"), needs_a_model=True)
# --- Structure and knowledge ----------------------------------------------------------------------
# Reads the text already there (and the thumbnails), so it comes after reading (`finddocs.recipe-step`, #5550).
_job("find-documents-in-a-folder", {READING}, {"document_groups"}, "structure", _LIST, ("accept_above",), needs_a_model=False)
# Splits the text already read, a page's or its lines', so it comes after reading (#5581).
_job("split-into-entries", {READING}, {"entries"}, "structure", _LIST, ("model",), needs_a_model=True)
_job("find-names-tag-words", {READING}, {"mentions"}, "entities", _LIST, ("model",), needs_a_model=True)
_job("find-statements", {READING, "mentions"}, {"claims"}, "graph", _LIST, ("model", "prompt"), needs_a_model=True)
_job("work-out-dates", {"mentions"}, {"dates"}, "graph", _LIST, needs_a_model=False)
_job("link-to-authorities", {"mentions"}, {"authority_links"}, "graph", _LIST, ("sources",), needs_a_model=False)
_job("place-in-a-gazetteer", {"mentions"}, {"places"}, "places", _LIST, ("gazetteer",), needs_a_model=False)
# The embed job embeds the page's text, read line by line or given whole (`page_text_cache`, #5553).
_job("make-a-vector", {READING}, {"vectors"}, "vectors",
     "each model's top results for a few of your own questions", ("model",), needs_a_model=True)
_job("describe-for-the-catalogue", {"line_readings"}, {"metadata_values"}, "catalogue", _LIST, ("fields",), needs_a_model=False)
# A prototype's questions asked of each of its documents and entries, from the text already read; the answers land
# as the nodes' attributes, each citing its words (`structured.extract.step-in-a-recipe`, #5636).
_job("extract-to-a-table", {READING}, {"table_rows"}, "structure", _LIST, ("model", "prototype"), needs_a_model=True)
_job("pull-out-passages", {"line_readings"}, {"passages"}, "knowledge", _LIST, ("question",), needs_a_model=False)
_job("train-a-model", {"line_readings", "lines"}, {"model_card"}, "train",
     "the candidate against the current step on held-out corrected pages", ("base", "where"), needs_a_model=False)
# --- Output ---------------------------------------------------------------------------------------
# One job for every layer: which layer it checks (readings, names, statements, links) is a setting,
# so `takes` names only what every check needs, the readings the proposals came from.
_job("check", {READING}, {"verdicts"}, "check", _LIST, ("layer", "model", "prompt"), needs_a_model=True)
_job("export", {READING}, {"files"}, "output", "the files side by side", ("formats", "folder"), needs_a_model=False)
_job("publish", {"files"}, {"published"}, "publish", "the published pages side by side", ("where",), needs_a_model=False)


# --- How each step with a model distils into a local model (`source.distil.each-step-has-a-method`, #5770) ---------


@dataclass(frozen=True)
class Distil:
    """A step's distil method: what makes the lessons (`teacher`), the local model it trains (`student`), the trainer
    that trains it, and how the student is measured against what it replaces. No student: `why` says why not."""
    teacher: str = ""
    student: str = ""
    trainer: str = ""
    measure: str = ""
    why: str = ""


_NOT_YET = "not built yet: no trainer for it in Fichero"
#: Ruled order of building: read-a-line, then review (correct), regions, names.
DISTIL: dict[str, Distil] = {
    "read-a-line": Distil(
        teacher="the lines a person corrected (#5700), else the readings of the reader the project uses",
        student="a Kraken reader, or a small MLX vision model by LoRA", trainer="training.local, Hugging Face Jobs",
        measure="character error rate on held-out corrected lines, beside the reader it replaces"),
    "find-regions": Distil(
        teacher="the regions a person drew or corrected", student="a YOLO layout model", trainer="training.yolo_local",
        measure="region agreement on held-out corrected pages"),
    "correct": Distil(why="not built yet: the thinking palaeographer's corrections as lessons (#4642)"),
    "find-names-tag-words": Distil(why="not built yet: Fichero has no spaCy trainer (#5536)"),
    "find-lines": Distil(why=_NOT_YET),
    "find-the-script": Distil(why=_NOT_YET),
    "refine-shapes": Distil(why=_NOT_YET),
    "find-signs": Distil(why=_NOT_YET),
    "find-a-tables-cells": Distil(why=_NOT_YET),
    "read-a-page": Distil(why="distilled as read-a-line: once lines exist, a page is read line by line"),
    "find-where-readers-disagree": Distil(why="nothing to distil: it compares the readers it is given"),
    "trace-a-drawing": Distil(why=_NOT_YET),
    "identify-signs": Distil(why=_NOT_YET),
    "transcribe-speech": Distil(why=_NOT_YET),
    "translate-transliterate-normalise": Distil(why=_NOT_YET),
    "split-into-entries": Distil(why=_NOT_YET),
    "find-statements": Distil(why=_NOT_YET),
    "make-a-vector": Distil(why="nothing to distil: the embedding model is chosen, not trained here"),
    "extract-to-a-table": Distil(why=_NOT_YET),
    "check": Distil(why="nothing to distil: a check is the teacher's own judgement of other steps"),
}


def starts_with(materials) -> frozenset[str]:
    """What a project of these materials starts with: the page's text as well only when all of it is already text."""
    given = set(materials or ())
    return TEXT_STARTS_WITH if given and given <= {"text"} else STARTS_WITH


def unmet_inputs(step_jobs: list[str | None], *, starts_with: frozenset[str] = STARTS_WITH) -> list[str]:
    """Check a recipe's steps in order: every step's inputs must be produced earlier (or be a page
    image, which every project starts with). Returns one plain sentence per problem; [] is clean.
    An unknown job is a problem too, named, so a recipe from a newer Fichero says what is missing."""
    have = set(starts_with)
    problems = []
    for index, job_id in enumerate(step_jobs, start=1):
        if job_id is None:  # not a step at all: the recipe check names it
            continue
        job = get_job(job_id)
        if job is None:
            problems.append(f"step {index}: this copy of Fichero has no job {job_id!r}")
            continue
        missing = sorted(" or ".join(kind.split("|")) for kind in job.takes if have.isdisjoint(kind.split("|")))
        if missing:
            problems.append(f"step {index} ({job.name}) needs {', '.join(missing)}, which no earlier step gives")
        have |= job.gives
    return problems
