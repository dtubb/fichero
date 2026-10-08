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
    if job.topic is None or job.topic.kind != "job":
        raise ValueError(f"job {job.id!r} has no entry in the topic registry: setup and the manual show it")
    _JOBS[job.id] = job
    return job


def get_job(job_id: str) -> Job | None:
    return _JOBS.get(job_id)


def all_jobs() -> list[Job]:
    return list(_JOBS.values())


def _job(id, takes, gives, layer, compare, settings=()):  # noqa: A002
    return register_job(Job(id, frozenset(takes), frozenset(gives), layer, compare,
                            settings=tuple(settings)))


_TEXT = "a text diff of the readings, with character and word error rates where pages are corrected"
_BOXES = "the shapes side by side, with precision and recall against shapes a person has checked"
_LIST = "the two lists side by side, with precision and recall where a person has confirmed some"

# --- Reading jobs ---------------------------------------------------------------------------------
_job("prepare-the-image", {"page_image"}, {"page_image", "rendition"}, "prepare", "the renditions side by side",
     ("operations",))
_job("split-pages", {"page_image"}, {"page_image"}, "prepare", "the cut pages side by side")
_job("find-regions", {"page_image"}, {"regions"}, "lines", _BOXES, ("model",))
_job("find-lines", {"page_image"}, {"lines"}, "lines", _BOXES, ("model", "regions"))
_job("put-in-order", {"lines"}, {"reading_order"}, "lines", "the two orders side by side")
_job("refine-shapes", {"page_image", "lines"}, {"lines"}, "lines", _BOXES, ("model",))
_job("find-signs", {"page_image"}, {"signs"}, "lines", _BOXES, ("model",))
_job("find-a-tables-cells", {"regions"}, {"table_cells"}, "lines", _BOXES, ("model",))
_job("read-a-line", {"lines"}, {"line_readings"}, "reading", _TEXT, ("model", "prompt"))
_job("read-a-page", {"page_image"}, {"page_reading"}, "reading", _TEXT, ("model", "prompt"))
_job("tie-text-to-lines", {"page_reading", "lines"}, {"line_readings"}, "reading", _TEXT)
_job("correct", {"line_readings"}, {"line_readings"}, "reading", _TEXT, ("model", "prompt", "only_below_confidence"))
_job("trace-a-drawing", {"regions"}, {"drawings"}, "reading", "the drawings side by side", ("model",))
_job("identify-signs", {"signs"}, {"sign_identifications"}, "reading", _LIST, ("model",))
_job("transcribe-speech", {"recording"}, {"line_readings"}, "reading", _TEXT, ("model",))
_job("translate-transliterate-normalise", {"line_readings"}, {"line_readings"}, "reading", _TEXT, ("model", "target"))
# --- Structure and knowledge ----------------------------------------------------------------------
# Reads the text already there (and the thumbnails), so it comes after reading (`finddocs.recipe-step`, #5550).
_job("find-documents-in-a-folder", {READING}, {"document_groups"}, "structure", _LIST, ("accept_above",))
# Splits the text already read, a page's or its lines', so it comes after reading (#5581).
_job("split-into-entries", {READING}, {"entries"}, "structure", _LIST, ("model",))
_job("find-names-tag-words", {READING}, {"mentions"}, "entities", _LIST, ("model",))
_job("find-statements", {READING, "mentions"}, {"claims"}, "graph", _LIST, ("model", "prompt"))
_job("work-out-dates", {"mentions"}, {"dates"}, "graph", _LIST)
_job("link-to-authorities", {"mentions"}, {"authority_links"}, "graph", _LIST, ("sources",))
_job("place-in-a-gazetteer", {"mentions"}, {"places"}, "places", _LIST, ("gazetteer",))
_job("make-a-vector", {"line_readings"}, {"vectors"}, "vectors",
     "each model's top results for a few of your own questions", ("model",))
_job("describe-for-the-catalogue", {"line_readings"}, {"metadata_values"}, "catalogue", _LIST, ("fields",))
_job("extract-to-a-table", {"line_readings"}, {"table_rows"}, "structure", _LIST, ("fields",))
_job("pull-out-passages", {"line_readings"}, {"passages"}, "knowledge", _LIST, ("question",))
_job("train-a-model", {"line_readings", "lines"}, {"model_card"}, "train",
     "the candidate against the current step on held-out corrected pages", ("base", "where"))
# --- Output ---------------------------------------------------------------------------------------
# One job for every layer: which layer it checks (readings, names, statements, links) is a setting,
# so `takes` names only what every check needs, the readings the proposals came from.
_job("check", {READING}, {"verdicts"}, "check", _LIST, ("layer", "model", "prompt"))
_job("export", {READING}, {"files"}, "output", "the files side by side", ("formats", "folder"))
_job("publish", {"files"}, {"published"}, "output", "the published pages side by side", ("where",))


def unmet_inputs(step_jobs: list[str], *, starts_with: frozenset[str] = STARTS_WITH) -> list[str]:
    """Check a recipe's steps in order: every step's inputs must be produced earlier (or be a page
    image, which every project starts with). Returns one plain sentence per problem; [] is clean.
    An unknown job is a problem too, named, so a recipe from a newer Fichero says what is missing."""
    have = set(starts_with)
    problems = []
    for index, job_id in enumerate(step_jobs, start=1):
        job = get_job(job_id)
        if job is None:
            problems.append(f"step {index}: this copy of Fichero has no job {job_id!r}")
            continue
        missing = sorted(" or ".join(kind.split("|")) for kind in job.takes if have.isdisjoint(kind.split("|")))
        if missing:
            problems.append(f"step {index} ({job.name}) needs {', '.join(missing)}, which no earlier step gives")
        have |= job.gives
    return problems
