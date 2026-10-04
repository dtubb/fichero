"""The job registry: what each job takes, what it gives, and how it explains itself.

`source/models-chains-and-projects.md` section 2 (`source.recipe.jobs-are-a-registry`,
`source.recipe.steps-are-jobs`). A recipe is written in jobs, not tools: each step names a job, and
because every job declares the KINDS of thing it takes and gives, a recipe can be checked before it
runs (a step may only use what an earlier step produced). The registry is open: a feature adds a
job by calling `register_job`, and recipes, onboarding, the activity queue and the recipe check
pick it up with no other change. Each job's `description` is the plain text setup, the Inspector,
the recipe README and the user manual show (`source.onboard.*`, "What onboarding teaches").

A job is not a tool: the workflow tools (`workflows/registry.py`) are how a job is carried out;
a job is what a recipe asks for.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# The kinds of thing that flow between jobs. A page image is what every project starts with.
STARTS_WITH = frozenset({"page_image"})
#: A `takes` entry may name kinds joined by "|": any one of them meets it (`source.chain.checked-before-run`).
READING = "line_readings|page_reading"


@dataclass(frozen=True)
class Job:
    """One registered job."""

    id: str
    name: str
    takes: frozenset[str]
    gives: frozenset[str]
    layer: str
    #: How two runs of this job are compared in an A/B (section 8a).
    compare: str
    #: What it does and why a recipe includes it, in a researcher's words.
    description: str
    #: The Fichero version that added it, so a recipe naming a job this copy lacks can say which has it.
    since: str = "2026.10.03"
    settings: tuple[str, ...] = field(default_factory=tuple)


_JOBS: dict[str, Job] = {}


def register_job(job: Job) -> Job:
    """Add a job. A second registration of one id is a mistake, not an update."""
    if job.id in _JOBS:
        raise ValueError(f"job {job.id!r} is already registered")
    if not job.description.strip():
        raise ValueError(f"job {job.id!r} has no description: setup and the manual show it")
    _JOBS[job.id] = job
    return job


def get_job(job_id: str) -> Job | None:
    return _JOBS.get(job_id)


def all_jobs() -> list[Job]:
    return list(_JOBS.values())


def _job(id, name, takes, gives, layer, compare, description, settings=()):  # noqa: A002
    return register_job(Job(id, name, frozenset(takes), frozenset(gives), layer, compare,
                            description, settings=tuple(settings)))


_TEXT = "a text diff of the readings, with character and word error rates where pages are corrected"
_BOXES = "the shapes side by side, with precision and recall against shapes a person has checked"
_LIST = "the two lists side by side, with precision and recall where a person has confirmed some"

# --- Reading jobs ---------------------------------------------------------------------------------
_job("prepare-the-image", "Prepare the image", {"page_image"}, {"page_image", "rendition"}, "prepare",
     "the renditions side by side",
     "Crops, straightens, rotates or brightens a page and keeps the result as a new version of the "
     "image; the original is never changed. Damaged or faded pages read far better prepared.",
     ("operations",))
_job("split-pages", "Split pages", {"page_image"}, {"page_image"}, "prepare", "the cut pages side by side",
     "Cuts a scan of an open book (two pages at once) into single pages, in order.")
_job("find-documents-in-a-folder", "Find documents in a folder", {"page_image"}, {"document_groups"}, "prepare", _LIST,
     "Proposes which pages belong together as one document, such as a letter of three pages in an "
     "archive bundle, for you to confirm.")
_job("find-regions", "Find regions", {"page_image"}, {"regions"}, "lines", _BOXES,
     "Finds the blocks on a page (main text, margins, tables, headings, drawings) so each kind can "
     "be read the right way.", ("model",))
_job("find-lines", "Find lines", {"page_image"}, {"lines"}, "lines", _BOXES,
     "Finds each line of writing and its baseline, so a line reader can read it. Kraken does this "
     "on your Mac for free.", ("model", "regions"))
_job("put-in-order", "Put in order", {"lines"}, {"reading_order"}, "lines", "the two orders side by side",
     "Works out the order the lines are read in, across columns and margins.")
_job("refine-shapes", "Refine shapes", {"page_image", "lines"}, {"lines"}, "lines", _BOXES,
     "Tightens rough boxes from one model with a more precise detector.", ("model",))
_job("find-signs", "Find signs", {"page_image"}, {"signs"}, "lines", _BOXES,
     "Finds each sign on a tablet, seal or page, for scripts read sign by sign.", ("model",))
_job("find-a-tables-cells", "Find a table's cells", {"regions"}, {"table_cells"}, "lines", _BOXES,
     "Finds the rows, columns and cells of a table.", ("model",))
_job("read-a-line", "Read each line", {"lines"}, {"line_readings"}, "reading", _TEXT,
     "Reads each line on its own. Line readers (Kraken, Tesseract for print) are fast, run on your "
     "Mac, and can be trained on your own corrected pages.", ("model", "prompt"))
_job("read-a-page", "Read a page", {"page_image"}, {"page_reading"}, "reading", _TEXT,
     "Reads a whole page at once, usually with a vision model. Strong on hard pages, but it does not "
     "keep where each line was.", ("model", "prompt"))
_job("tie-text-to-lines", "Tie text to lines", {"page_reading", "lines"}, {"line_readings"}, "reading",
     _TEXT, "Places a page's text onto its found lines, line by line, so each line knows its words.")
_job("correct", "Correct", {"line_readings"}, {"line_readings"}, "reading", _TEXT,
     "A second model checks each reading against the picture and proposes corrections, kept as new "
     "readings beside the first.", ("model", "prompt", "only_below_confidence"))
_job("trace-a-drawing", "Trace a drawing", {"regions"}, {"drawings"}, "reading", "the drawings side by side",
     "Redraws a drawing, map or seal as a clean vector picture.", ("model",))
_job("identify-signs", "Identify signs", {"signs"}, {"sign_identifications"}, "reading", _LIST,
     "Proposes which sign each mark is, with how sure it is, for a person to confirm.", ("model",))
_job("transcribe-speech", "Transcribe speech", {"recording"}, {"line_readings"}, "reading", _TEXT,
     "Turns recorded speech into text with its timings.", ("model",))
_job("translate-transliterate-normalise", "Translate, transliterate or normalise", {"line_readings"}, {"line_readings"}, "reading",
     _TEXT, "Makes a second reading in modern spelling, another script or another language, beside the "
     "original, never over it.", ("model", "target"))
# --- Structure and knowledge ----------------------------------------------------------------------
_job("split-into-entries", "Split into entries", {"line_readings"}, {"entries"}, "structure", _LIST,
     "Splits a diary, register or ledger into its dated entries.")
_job("find-names-tag-words", "Find names", {READING}, {"mentions"}, "entities", _LIST,
     "Finds the people, places, dates and things named in the text.", ("model",))
_job("find-statements", "Find statements", {READING, "mentions"}, {"claims"}, "graph", _LIST,
     "Finds who did what to whom (sold, gave, owed, married), each tied to the words it came from.",
     ("model", "prompt"))
_job("work-out-dates", "Work out dates", {"mentions"}, {"dates"}, "graph", _LIST,
     "Turns dates as written (feast days, regnal years, any calendar) into exact dates.")
_job("link-to-authorities", "Link to authorities", {"mentions"}, {"authority_links"}, "graph", _LIST,
     "Proposes links from people and places to Wikidata, VIAF, GeoNames or your own list, for you to "
     "confirm.", ("sources",))
_job("place-in-a-gazetteer", "Place in a gazetteer", {"mentions"}, {"places"}, "places", _LIST,
     "Gives each place its coordinates and a gazetteer identifier, naming the gazetteer.", ("gazetteer",))
_job("make-a-vector", "Make vectors for search", {"line_readings"}, {"vectors"}, "vectors",
     "each model's top results for a few of your own questions",
     "Lets you search by meaning, not only by words. Chosen for your languages.", ("model",))
_job("describe-for-the-catalogue", "Describe for the catalogue", {"line_readings"}, {"metadata_values"},
     "catalogue", _LIST,
     "Proposes values for your catalogue fields from the page, for you to confirm. Facts only.",
     ("fields",))
_job("extract-to-a-table", "Extract to a table", {"line_readings"}, {"table_rows"}, "structure", _LIST,
     "Fills one row per document or entry with your fields (for a sale record: seller, buyer, the "
     "person sold, price, date, place), each value tied to its text; exports as a spreadsheet.",
     ("fields",))
_job("pull-out-passages", "Pull out passages", {"line_readings"}, {"passages"}, "knowledge", _LIST,
     "Gathers the passages on a question or theme, each with its source.", ("question",))
_job("train-a-model", "Train a model", {"line_readings", "lines"}, {"model_card"}, "train",
     "the candidate against the current step on held-out corrected pages",
     "Trains a small model on your corrected pages, so it reads your material better and faster. "
     "A Kraken reader or a YOLO detector trains on this Mac; larger models on Hugging Face Jobs or a "
     "cluster, if the project lets pages leave the Mac.", ("base", "where"))
# --- Output ---------------------------------------------------------------------------------------
# One job for every layer: which layer it checks (readings, names, statements, links) is a setting,
# so `takes` names only what every check needs, the readings the proposals came from.
_job("check", "Check", {READING}, {"verdicts"}, "check", _LIST,
     "A person or a checker model confirms, corrects or rejects each proposal of a layer, with its reasons; a model's "
     "check is recorded as that model's, never as a person's.", ("layer", "model", "prompt"))
_job("export", "Export", {READING}, {"files"}, "output", "the files side by side",
     "Writes your work out in the formats you name (TEI, PAGE, ALTO, plain text, Markdown, Excel, "
     "RDF, a website), kept up to date if you choose a synced folder.", ("formats", "folder"))
_job("publish", "Publish", {"files"}, {"published"}, "output", "the published pages side by side",
     "Publishes a folder as IIIF or a static website.", ("where",))


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
