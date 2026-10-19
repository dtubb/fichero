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

STAGES: tuple[Stage, ...] = (
    Stage("prepare-images", "Prepare Images", ("split-pages", "prepare-the-image"),
          "Splits two-page scans into single pages and straightens, crops or brightens a page, keeping the original.",
          "A photograph of an open notebook becomes its left and right pages.",
          (Question("two_pages_per_image", "Two pages per image?", "yes-no", default=False),
           Question("prepare", "Straighten, crop, brighten?", "many",
                    (("straighten", "Straighten"), ("crop", "Crop"), ("brighten", "Brighten")), default=[]))),
    Stage("find-regions", "Find Regions", ("find-regions",),
          "Finds the blocks on each page: columns, notes in the margin, headings, tables and pictures.",
          "A two-column page with a note in the margin: three blocks, the note kept apart.",
          (Question("layout", "Columns, margins and glosses? Tables on the pages?", "many",
                    (("columns", "Columns"), ("margins", "Notes in the margins"), ("glosses", "Glosses between lines"),
                     ("tables", "Tables"), ("forms", "Forms")), default=[]),
           Question("mixed_writing", "Handwriting and print on the same page?", "yes-no", default=False,
                    read_by_a_step=False))),
    Stage("find-lines", "Find Lines", ("find-lines", "put-in-order", "refine-shapes"),
          "Finds the lines of writing in each block and the order to read them in.",
          "The left column's lines, then the right's, each traced along its baseline.",
          ()),
    Stage("read", "Read", ("read-a-line", "read-a-page", "correct", "tie-text-to-lines", "find-where-readers-disagree"),
          "Reads the writing line by line, and can correct it with a second model.",
          "“Juan de la Cruz vende una casa” read from its line, ready to correct.",
          # Lines are read one by one; "or the page at once?" was dropped (ruled 2026-10-18, #5788).
          (Question("correct_with_a_second_model", "Have a second model check the reading? Slower and more accurate; may cost if it runs in the cloud.", "yes-no", default=False),)),
    Stage("normalise", "Normalise", ("translate-transliterate-normalise",),
          "Writes the text again in the same language at another level: as written (a diplomatic reading), "
          "abbreviations expanded, spelling normalised, or modernised.",
          "“q̃ dho” written out as “que dicho”.",
          (Question("normalise_how_far", "Into what?", "many", _LEVELS, default=["as_written"], read_by_a_step=True),),
          needs=("read",)),
    # ponytail: Translate shares Normalise's job until a translation job of its own exists; `stage_of` names Normalise.
    Stage("translate", "Translate", ("translate-transliterate-normalise",),
          "Translates the text into another language, any language you choose.",
          "“vende una casa” as “sells a house”.",
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
          "“Juan de la Cruz” and “Istmina” marked, Istmina placed on the map.",
          (Question("entity_kinds", "Which kinds of names?", "many",
                    (("people", "People"), ("places", "Places"), ("organisations", "Organisations"), ("dates", "Dates"),
                     ("things", "Things (objects, goods)"), ("events", "Events")),
                    default=["people", "places", "organisations"], read_by_a_step=True),
           Question("gazetteer", "Which place list? GeoNames (worldwide, modern names) · Wikidata · My own list", "one",
                    (("geonames", "GeoNames"), ("wikidata", "Wikidata"), ("project", "The project's own list")),
                    default="geonames", read_by_a_step=True)),
          needs=("read",)),
    Stage("statements", "Statements", ("find-statements",),
          "Finds who did what to whom, as statements you can check: a sale, a gift, a marriage, a letter sent.",
          "“Juan de la Cruz sells a house to María Mosquera”.",
          (Question("statement_kinds", "Which kinds of statements?", "many",
                    (("sales", "Sales"), ("gifts", "Gifts"), ("marriages", "Marriages"), ("letters", "Letters sent"),
                     ("other", "Anything else")), default=["sales", "gifts", "marriages", "letters", "other"]),),
          needs=("read", "names")),
    Stage("dates", "Dates & Times", ("work-out-dates",),
          "Works out the dates the names step found, in the calendar they were written in.",
          "“a 3 de mayo de 1740” as 1740-05-03.",
          (Question("calendars", "Which calendars?", "many",
                    (("gregorian", "Gregorian"), ("julian", "Julian"), ("regnal", "Regnal years"),
                     ("french-republican", "French Republican")), default=["gregorian"]),),
          needs=("names",)),
    Stage("passages", "Passages", ("pull-out-passages",),
          "Pulls out the passages you ask for: quotations, formulae, a party's own words.",
          "The notary's closing formula on each deed.",
          (Question("passage_kinds", "Which kinds of passages?", "many",
                    (("quotations", "Quotations"), ("formulae", "Formulae"), ("own-words", "A party's own words")),
                    default=["quotations"]),),
          needs=("read",)),
    Stage("structured-data", "Structured Data", ("find-a-tables-cells", "extract-to-a-table", "describe-for-the-catalogue"),
          "Fills a table or a catalogue record from the pages: a ledger's columns, a deed's parties and date.",
          "Each deed's buyer, seller, price and date as one row.",
          (Question("fields", "Which fields to fill, and from what?", "text", default=""),),
          needs=("read",)),
    Stage("search", "Search", ("make-a-vector",),
          "Makes the pages searchable by meaning as well as by their words.",
          "Searching “sale of land” finds “venta de un solar”.",
          (),
          needs=("read",)),
)

#: The stages a sample run can try (`POST /api/recipes/stages/{stage}/try`): Find Lines and Read by the bake-off, the
#: others by their workflow on the samples.
TRIED_BY_THE_BAKEOFF = frozenset({"find-lines", "read"})
#: Tried by their own steps run straight on the copy, not through a workflow: Organise's Find the Documents and
#: Split into entries (`source.onboard.stages.organise-tried-on-a-run`, #5668).
TRIED_ON_ITS_OWN = frozenset({"organise", "find-regions"})


def get_stage(stage_id: str) -> Stage | None:
    return next((s for s in STAGES if s.id == stage_id), None)


def stage_of(job: str) -> Stage | None:
    return next((s for s in STAGES if job in s.jobs), None)


def sampleable(stage: Stage) -> bool:
    from fichero_server.recipes.start import WORKFLOW_FOR_JOB

    return (stage.id in TRIED_BY_THE_BAKEOFF or stage.id in TRIED_ON_ITS_OWN
            or any(j in WORKFLOW_FOR_JOB for j in stage.jobs))


def listing(recipe: dict[str, Any] | None, answers: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """The thirteen stages, in pipeline order, each on or off in this project's recipe, with its questions (answered where the
    project has answered them, else their defaults) and its needs in words."""
    in_recipe = {str(s.get("job")) for s in (recipe or {}).get("steps") or []}
    answered = dict((answers or {}).get("job_answers") or {})
    titles = {s.id: s.title for s in STAGES}
    out = []
    for stage in STAGES:
        out.append({
            "id": stage.id, "title": stage.title, "sentence": stage.sentence, "example": stage.example,
            "jobs": list(stage.jobs), "on": bool(in_recipe & set(stage.jobs)),
            "jobs_in_recipe": [j for j in stage.jobs if j in in_recipe],
            "questions": [{"key": q.key, "ask": q.ask, "kind": q.kind,
                           "options": [{"id": i, "title": t} for i, t in q.options], "default": q.default,
                           "answer": answered.get(q.key, q.default), "read_by_a_step": q.read_by_a_step}
                          for q in stage.questions],
            "needs": [{"stage": n, "why": f"{stage.title} needs {titles[n]}"} for n in stage.needs],
            "sampleable": sampleable(stage), "tried_by": "bake-off" if stage.id in TRIED_BY_THE_BAKEOFF else "workflow",
        })
    return out
