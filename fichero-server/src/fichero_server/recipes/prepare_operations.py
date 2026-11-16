"""Prepare Images as four steps the person leaves in or out (`wide.prepare.*`, #5382, #5580; section C of wide-onboarding.md).

The stage keeps its two jobs (`split-pages`, `prepare-the-image`) and its four questions; this module is the one place that says
which operations there are, what each does, which are on by default from the questions, and which the person's hand switched
(`answers.job_answers.prepare_operations`, the ids that are on). The Set Up listing, the Start plan and the run all read it, so
none of them works the answer out twice. Nothing here does a picture's work: the operations map onto `page_crop` and `prepare`.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

#: The answer's key in `answers.job_answers`: the ids of the operations that are on, set by hand.
ANSWER = "prepare_operations"
SPLIT, STRAIGHTEN, CROP, CLARITY = "split", "straighten", "crop", "clarity"
#: The operations the `prepare` card runs (split is its own job, the `split-pages` workflow).
PREPARE_OPERATIONS = (STRAIGHTEN, CROP, CLARITY)
#: The words on Clarity's row when the paper answer is empty and the run looks at each page (ruled 2026-10-31, Q5).
CLARITY_LOOKS_AT_EACH = "Fichero looks at each page and raises only the faded ones"


@dataclass(frozen=True)
class Operation:
    id: str
    title: str
    sentence: str


#: In ScanTailor's order (section C). The sentences are the engine's words; the app draws them.
OPERATIONS: tuple[Operation, ...] = (
    Operation(SPLIT, "Split a book photograph",
              "Cuts a photograph of two pages at the gutter into its left and right pages."),
    Operation(STRAIGHTEN, "Straighten",
              "Turns a page upright by its text and straightens the lines (a quarter turn, then up to 15 degrees)."),
    Operation(CROP, "Crop to the paper",
              "Finds the paper, cuts away the table, ruler and colour card, and squares a page photographed at an angle; "
              "flattens a page curved into the gutter. Blank pages are marked here."),
    Operation(CLARITY, "Clarity",
              "Brightens, raises the contrast and sharpens faded or dim writing on a new copy."),
)
#: The rest of the suite (`image.ops.recipe-designer-offers-every-operation`), in the suite's order: each is the engine step of that
#: name (`workflows/tools/enhance_step_nodes.SPECS`), off until the hand switches it on. Ruled lines and bleed-through are not here:
#: the paper answers run them (`prepare_run.PAPER_STEPS`).
_EXTRA = (
    ("stain-flatten", "Flatten stains", "Evens out stains and discolouration so the writing stands clear of them."),
    ("sharpen", "Sharpen", "Sharpens soft or blurred writing."),
    ("denoise", "Remove speckle", "Cleans speckle and scanner noise from the page."),
    ("binarise", "Binarise", "Turns the page to black writing on white, for readers that want a clean two-tone page."),
    ("flip", "Flip", "Mirrors the page left to right (a page photographed in a mirror or from behind glass)."),
    ("grayscale", "Grayscale", "Drops the colour and keeps the tones."),
    ("auto-levels", "Auto levels", "Stretches the page's darkest and lightest tones to fill the range."),
)
EXTRA = tuple(e[0] for e in _EXTRA)
#: The audited action each runs through (`image.ops.one-action-per-operation`).
ACTION_OF = {i: "image." + i.replace("-", "_") for i in EXTRA} | {"flip": "image.flip_horizontal"}
OPERATIONS = OPERATIONS + tuple(Operation(*e) for e in _EXTRA)
IDS = tuple(o.id for o in OPERATIONS)


def chosen(job_answers: dict[str, Any] | None) -> list[str] | None:
    """The operations the person switched by hand (a list of ids), None when they never did."""
    said = (job_answers or {}).get(ANSWER)
    return [i for i in said if i in IDS] if isinstance(said, list) else None


def _paper(job_answers: dict[str, Any] | None) -> list[str]:
    paper = (job_answers or {}).get("the_paper")
    return [str(p) for p in paper] if isinstance(paper, list) else []


def defaults(job_answers: dict[str, Any] | None) -> dict[str, bool]:
    """Each operation's default from the questions: split when two pages share a picture, clarity unless the paper answer
    names paper and does not say faded (no answer: the run looks at each page, so it is on), straighten and crop always."""
    from fichero_server.recipes.prepare import runs_contrast

    return {SPLIT: (job_answers or {}).get("two_pages_per_image") is True, STRAIGHTEN: True, CROP: True,
            CLARITY: runs_contrast(_paper(job_answers)), **{i: False for i in EXTRA}}


def on(job_answers: dict[str, Any] | None) -> dict[str, bool]:
    """Each operation on or off: the hand's choice where there is one, else the default (the hand wins over the question)."""
    by_default = defaults(job_answers)
    by_hand = chosen(job_answers)
    return {i: (i in by_hand if by_hand is not None else by_default[i]) for i in IDS}


def listing(job_answers: dict[str, Any] | None) -> list[dict[str, Any]]:
    """The operations as the stage listing serves them: id, title, the engine's sentence, the default, whether it is on and
    whether the person's hand set it, and a note where the row needs a word."""
    by_default, now, by_hand = defaults(job_answers), on(job_answers), chosen(job_answers) is not None
    out = []
    for op in OPERATIONS:
        note = CLARITY_LOOKS_AT_EACH if op.id == CLARITY and not _paper(job_answers) else None
        out.append({"id": op.id, "title": op.title, "sentence": op.sentence, "default": by_default[op.id],
                    "on": now[op.id], "by_hand": by_hand, "note": note})
    return out


def split_is_off(job_answers: dict[str, Any] | None) -> bool:
    """Whether the split is an explicit no (it takes `split-pages` out of the plan): the hand left it out, else the two-pages
    question was answered no. No answer at all keeps today's behaviour, so an older project does not change."""
    by_hand = chosen(job_answers)
    if by_hand is not None:
        return SPLIT not in by_hand
    return (job_answers or {}).get("two_pages_per_image") is False


def to_run(job_answers: dict[str, Any] | None, paper: list[str] | None = None) -> list[str]:
    """The operations the `prepare` card runs, in order. The hand's choice exactly; else crop and straighten, and clarity
    where the paper answer allows (`prepare.runs_contrast`)."""
    from fichero_server.recipes.prepare import runs_contrast

    by_hand = chosen(job_answers)
    if by_hand is not None:
        return [i for i in (*PREPARE_OPERATIONS, *EXTRA) if i in by_hand]
    return [i for i in PREPARE_OPERATIONS if i != CLARITY or runs_contrast(paper)]
