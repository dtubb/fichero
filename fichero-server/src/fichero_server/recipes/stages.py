"""The stages of Set Up, one page each (section 7c, ruled 2026-10-11, #5668).

One list the setup window, the Inspector and the manual read (`source.onboard.stages.stages-list-from-the-engine`):
each stage's id, title, sentence and example, the registry jobs it carries, its own questions (each saved as a
`job_answers` key, its default filled in), the stages it needs and why in words, and whether it can be tried on the
sample pages. The app works none of it out. The stages are listed in the order of section 7c's left list; the recipe
keeps the job registry's step order whatever order they are chosen in.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from fichero_server.recipes.examples import example_credit


@dataclass(frozen=True)
class Question:
    #: The answer's key in `answers.job_answers`.
    key: str
    ask: str
    #: one (a single choice), many (checkboxes), yes-no, text.
    kind: str
    options: tuple[tuple[str, str], ...] = ()
    default: Any = None
    #: True when a step reads it today (`start.JOB_ANSWER_SETTINGS`); the others are kept with the answers, for the
    #: stage's own use as it is built.
    read_by_a_step: bool = False
    #: A question that names kinds (#5805): every kind by default (an empty answer), the person can type their own, no
    #: fixed `options`, and the listing's `suggestions` hold only what a sample try found.
    open_ended: bool = False


@dataclass(frozen=True)
class Stage:
    id: str
    title: str
    jobs: tuple[str, ...]
    sentence: str
    example: str
    questions: tuple[Question, ...] = ()
    needs: tuple[str, ...] = field(default_factory=tuple)


_LEVELS = (("as_written", "As written"), ("expanded", "Abbreviations expanded"), ("regularised", "Normalised spelling"),
           ("modernised", "Modernised"))

#: The kinds of names the extraction has a section for, in the words a researcher uses.
NAME_KINDS = (("people", "People"), ("places", "Places"), ("organisations", "Organisations"), ("dates", "Dates and times"),
              ("events", "Events"))

STAGES: tuple[Stage, ...] = (
    Stage("prepare-images", "Prepare Images", ("split-pages", "prepare-the-image"),
          "Splits two-page scans into single pages and straightens, crops or brightens a page, keeping the original.",
          "A photograph of an open notebook becomes its left and right pages.",
          (Question("two_pages_per_image", "Two pages per image?", "yes-no", default=False),
           Question("prepare", "Straighten, crop, brighten?", "many",
                    (("straighten", "Straighten"), ("crop", "Crop"), ("brighten", "Brighten")), default=[]))),
    Stage("find-regions", "Find Regions", ("find-regions",),
          "Finds the blocks on each page: columns, notes in the margin, headings, tables and pictures.",
          "One block of text, a note in the margin and the folio number: three blocks, the note kept apart.",
          (Question("layout", "Columns, margins and glosses? Tables on the pages?", "many",
                    (("columns", "Columns"), ("margins", "Notes in the margins"), ("glosses", "Glosses between lines"),
                     ("tables", "Tables"), ("forms", "Forms")), default=[]),
           Question("mixed_writing", "Handwriting and print on the same page?", "yes-no", default=False,
                    read_by_a_step=False))),
    Stage("find-lines", "Find Lines", ("find-lines", "put-in-order", "refine-shapes"),
          "Finds the lines of writing in each block and the order to read them in.",
          "The block's lines from the top down, each traced along its baseline, in the order they are read.",
          ()),
    Stage("leave-out", "Leave Out", ("leave-out",),
          "Marks what is not writing as left out, before it is read: marks too small to be a line, anything off the page, and "
          "damage that only looks like writing. Nothing is deleted; you can bring any line back.",
          "A speck, a dark edge of the scanner bed and a stain are left out, each with its reason; the lines of writing are kept.",
          ()),
    Stage("read", "Read", ("read-a-line", "read-a-page", "correct", "tie-text-to-lines", "find-where-readers-disagree"),
          "Reads the writing line by line, and can correct it with a second model.",
          "“enel tþo q́ el escriuio, yental caso” read from its first line, ready to correct.",
          # Lines are read one by one; "or the page at once?" was dropped (ruled 2026-10-18, #5788).
          (Question("correct_with_a_second_model", "Have a second model check the reading? Slower and more accurate; may cost if it runs in the cloud.", "yes-no", default=False),
           # Kraken, then a model for the unsure lines (variant A, #5894): the bar the step reads as `only_below_confidence`.
           Question("review_certainty_bar", "Send the second model only the lines Kraken is unsure of?", "one",
                    (("whole-page", "No: it checks the whole page"), ("0.5", "Only lines under 0.5 sure"),
                     ("0.6", "Only lines under 0.6 sure"), ("0.7", "Only lines under 0.7 sure"),
                     ("0.8", "Only lines under 0.8 sure"), ("0.9", "Only lines under 0.9 sure")),
                    default="whole-page", read_by_a_step=True))),
    Stage("normalise", "Normalise", ("translate-transliterate-normalise",),
          "Writes the text again in the same language at another level: as written (a diplomatic reading), "
          "abbreviations expanded, spelling normalised, or modernised.",
          "“tþo” written out as “tiempo”, “q́” as “que”.",
          (Question("normalise_how_far", "Into what?", "many", _LEVELS, default=["as_written"], read_by_a_step=True),),
          needs=("read",)),
    # ponytail: Translate shares Normalise's job until a translation job of its own exists; `stage_of` names Normalise.
    Stage("translate", "Translate", ("translate-transliterate-normalise",),
          "Translates the text into another language, any language you choose.",
          "“muchos Años despues” as “many years later”.",
          (Question("translate_into", "Into which language?", "language", default=""),),
          needs=("read",)),
    Stage("organise", "Organise", ("find-documents-in-a-folder", "split-into-entries"),
          "Finds which pages belong together as one document, and splits a diary or register into its entries.",
          "Three pages of one letter in a bundle, proposed as one document for you to confirm.",
          (Question("documents_per_folder", "Are several documents in one folder, or one document per folder?",
                    "one", (("several", "Several in one folder"), ("one", "One document per folder")),
                    default="several"),),
          needs=("read",)),
    Stage("names", "Names", ("find-names-tag-words", "place-in-a-gazetteer", "link-to-authorities"),
          "Finds the people, places and other names in the text, places them on a map and links them to authorities.",
          "“españa” marked as a place and placed on the map, “Impresores” as an organisation.",
          # Tick boxes in plain words, all ticked, with room to type another kind (`source.onboard.stages.names-kinds-are-tick-boxes`):
          # the ids are the extraction's own sections (`recipes/start._ENTITY_SECTIONS`).
          (Question("entity_kinds", "Which kinds of names?", "many", NAME_KINDS,
                    default=[i for i, _ in NAME_KINDS], read_by_a_step=True, open_ended=True),
           Question("gazetteer", "Which place list? GeoNames (worldwide, modern names) · Wikidata · My own list", "one",
                    (("geonames", "GeoNames"), ("wikidata", "Wikidata"), ("project", "The project's own list")),
                    default="geonames", read_by_a_step=True)),
          needs=("read",)),
    Stage("statements", "Statements", ("find-statements",),
          "Finds who did what to whom, as statements you can check: a sale, a gift, a marriage, a letter sent.",
          "“Historia” happened after the Passion of “Redentor”.",
          (Question("statement_kinds", "Which kinds of statements?", "many", default=[], read_by_a_step=False,
                    open_ended=True),),
          needs=("read", "names")),
    Stage("dates", "Dates & Times", ("work-out-dates",),
          "Works out the dates the names step found, in the calendar they were written in.",
          "“muchos Años despues” worked out as “many years later”.",
          (Question("calendars", "Which calendars?", "many", default=[], read_by_a_step=True, open_ended=True),),
          needs=("names",)),
    Stage("passages", "Passages", ("pull-out-passages",),
          "Pulls out the passages you ask for, of any kind, and keeps where each one sits on the page.",
          "“Autor del libro. M. ora sus no per=” and the line after it, kept where they sit on the page.",
          (Question("passage_kinds", "Which kinds of passages?", "many", default=[], read_by_a_step=False, open_ended=True),),
          needs=("read",)),
    Stage("structured-data", "Structured Data", ("find-a-tables-cells", "extract-to-a-table"),
          "Fills a table from the pages: one column for each field you name.",
          "The work, the speaker and the folio as one row: “Diálogo de la Lengua”, “M.”, “8”.",
          (Question("fields", "Which fields to fill, and from what?", "many", default=[], read_by_a_step=False, open_ended=True),),
          needs=("read",)),
    Stage("search", "Search", ("make-a-vector",),
          "Makes the pages searchable by meaning as well as by their words. What is embedded is each page's text as read (line by line, or given whole) and, separately, the claims and entities found in it; one search model serves the whole project.",
          "Searching “historia” finds the lines that say “Historia”.",
          (),
          needs=("read",)),
    # Last, at folder level, after every other stage (`catalogue.folder-description-fields`, #6087): no question, the
    # fields of the description are the archival ones.
    Stage("catalogue", "Catalogue", ("describe-for-the-catalogue",),
          "Describes each folder from what its pages say, as an archival record: title, dates, extent, creator, scope and "
          "content, language, access points, then a 150-200 word description written to the catalogue-writing guidance: it shows, "
          "it does not tell. It describes; it does not interpret.",
          "A folder of letters described as: Title, Dates 1782–1790, Extent 214 pages, Scope and content: letters between "
          "the named parties, in Spanish; Description: 214 pages of letters from Cádiz to Veracruz, 31 of them naming the same "
          "merchant, with 40 accounts bound in.",
          (),
          needs=("read",)),
)

#: The stages a sample run can try (`POST /api/recipes/stages/{stage}/try`): Find Lines and Read by the bake-off, the
#: others by their workflow on the samples.
TRIED_BY_THE_BAKEOFF = frozenset({"find-lines", "read"})
#: Tried by their own steps run straight on the copy, not through a workflow: Organise's Find the Documents and
#: Split into entries (`source.onboard.stages.organise-tried-on-a-run`, #5668).
TRIED_ON_ITS_OWN = frozenset({"organise", "find-regions"})


#: What a stage that cannot be tried on the sample pages says (`source.try.every-job`): plain, and no promise.
NOT_TRIED = "This one can't be tried on your pages yet: it runs at Start, and you can check what it made then."


def get_stage(stage_id: str) -> Stage | None:
    return next((s for s in STAGES if s.id == stage_id), None)


def stage_of(job: str) -> Stage | None:
    return next((s for s in STAGES if job in s.jobs), None)


def sampleable(stage: Stage) -> bool:
    from fichero_server.recipes.start import WORKFLOW_FOR_JOB

    return (stage.id in TRIED_BY_THE_BAKEOFF or stage.id in TRIED_ON_ITS_OWN
            or any(j in WORKFLOW_FOR_JOB for j in stage.jobs))


def _words(value: Any) -> list[str]:
    """A kinds answer as a list of words, each once and as typed: a list, or the text an earlier build kept (split at
    commas and line breaks)."""
    import re

    parts = value if isinstance(value, list) else re.split(r"[,\n]", value) if isinstance(value, str) else []
    seen: dict[str, str] = {}
    for part in parts:
        word = str(part).strip()
        if word:
            seen.setdefault(word.casefold(), word)
    return list(seen.values())


def suggested_kinds(stage_id: str, result: dict[str, Any] | None) -> list[str]:
    """The kinds a sample try found, for a kinds question to suggest and for nothing else (#5805): Names' are the types
    of the names it found; a stage whose try reports `found_kinds` is read as that. Empty before a try, and for a stage
    whose try does not say."""
    if not result:
        return []
    found = list(result.get("found_kinds") or [])
    if stage_id == "names":
        found += [n.get("type") for n in result.get("names") or [] if isinstance(n, dict)]
    return sorted(_words(found), key=str.casefold)


def example_from_samples(stage_id: str, result: dict[str, Any] | None) -> str | None:
    """The first passage a sample try found (Passages' example from the person's own pages), else None."""
    if stage_id != "passages" or not result:
        return None
    first = next(iter(result.get("passages") or []), None)
    text = first.get("text") if isinstance(first, dict) else first
    return str(text).strip() or None if text else None


def runs_or_by_hand(job: str) -> bool:
    """Whether Start runs this job by itself or a tool does it by hand: the jobs a stage offers to tick."""
    from fichero_server.recipes.start import BY_HAND_FIX, start_runs

    return start_runs(job) or job in BY_HAND_FIX


def offered(stage: Stage) -> bool:
    """Whether Set Up offers this stage: at least one of its jobs is one Start runs by itself, or one that has a way to
    do it by hand. A stage whose every job has no tool yet asks its questions for nothing, so it waits for its job."""
    return any(runs_or_by_hand(job) for job in stage.jobs)


def listing(recipe: dict[str, Any] | None, answers: dict[str, Any] | None = None,
            tried: dict[str, dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """The thirteen stages, in pipeline order, each on or off in this project's recipe, with its questions (answered where the
    project has answered them, else their defaults) and its needs in words. `tried` is each stage's sample result, where
    it has one: what a kinds question suggests and Passages' example come from it and from nothing else."""
    in_recipe = {str(s.get("job")) for s in (recipe or {}).get("steps") or []}
    answered = dict((answers or {}).get("job_answers") or {})
    titles = {s.id: s.title for s in STAGES}
    tried = tried or {}
    out = []
    for stage in STAGES:
        if not offered(stage):  # a stage whose job nothing runs yet is not offered (`source.job.pull-out-passages`)
            continue
        result = tried.get(stage.id)
        out.append({
            "id": stage.id, "title": stage.title, "sentence": stage.sentence, "example": stage.example,
            "example_credit": example_credit(),
            "example_from_samples": example_from_samples(stage.id, result),
            # Only the jobs that run or can be done by hand: ticking Find Lines no longer ticks "Put in order" and
            # "Refine shapes", which nothing in Fichero does yet and Ready then listed as will-not-run (owner 2026-10-24).
            "jobs": [j for j in stage.jobs if runs_or_by_hand(j)], "on": bool(in_recipe & set(stage.jobs)),
            "jobs_in_recipe": [j for j in stage.jobs if j in in_recipe],
            "questions": [{"key": q.key, "ask": q.ask, "kind": q.kind,
                           "options": [{"id": i, "title": t} for i, t in q.options], "default": q.default,
                           "answer": _words(answered.get(q.key, q.default)) if q.open_ended else answered.get(q.key, q.default),
                           "read_by_a_step": q.read_by_a_step, "open_ended": q.open_ended,
                           "suggestions": suggested_kinds(stage.id, result) if q.open_ended else []}
                          for q in stage.questions],
            "needs": [{"stage": n, "why": f"{stage.title} needs {titles[n]}"} for n in stage.needs],
            "sampleable": sampleable(stage), "tried_by": "bake-off" if stage.id in TRIED_BY_THE_BAKEOFF else "workflow",
            "not_tried": None if sampleable(stage) else NOT_TRIED,
        })
    return out
