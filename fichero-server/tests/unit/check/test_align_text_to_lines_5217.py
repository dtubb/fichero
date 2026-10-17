"""`source.align.known-misalignments-fixture` and `source.align.below-threshold-stays-a-draft` (#5217, ruled 2026-10-17).

Spec: docs/contributor_manual/specs/source/models-chains-and-projects.md "Align Text to Lines, to the properly bar". The aligner alone
(`checking/tie_text`), over a real two-page fixture whose rough reads go wrong in known ways: a dropped line, two lines merged into one,
two lines reordered. Each case says what lands on which line and which lines are doubtful; a page too poorly aligned is a draft.
"""
from __future__ import annotations

from fichero_server.checking import tie_text

# A real two-page fixture: the first page of a colonial testament and the second (each line a line of the page's own text).
PAGE_ONE = ["En el nombre de Dios amen", "yo Juan Perez vezino desta ciudad", "estando enfermo del cuerpo", "y sano de la voluntad",
            "otorgo mi testamento"]
PAGE_TWO = ["Primeramente mando mi alma a Dios", "y mi cuerpo a la tierra", "y declaro por mis bienes", "unas casas en la calle real",
            "y un solar"]


def _text(lines):
    return "\n".join(lines)


def test_a_clean_read_ties_every_line_and_the_page_is_not_a_draft():
    """source.align.known-misalignments-fixture: the control, a faithful rough read gives every line its own words."""
    scored = tie_text.tie_lines(_text(PAGE_ONE), list(PAGE_ONE))

    assert [s["text"] for s in scored] == PAGE_ONE and all(s["tied"] for s in scored)
    assert tie_text.page_is_draft(scored) is False


def test_a_dropped_line_leaves_that_line_empty_and_flagged():
    """source.align.known-misalignments-fixture: the reader returned nothing for line 3; the neighbours keep their own words, line 3 is doubtful."""
    reads = list(PAGE_TWO)
    reads[2] = ""
    scored = tie_text.tie_lines(_text(PAGE_TWO), reads)

    assert [s["tied"] for s in scored] == [True, True, False, True, True]
    assert scored[0]["text"] == PAGE_TWO[0] and scored[3]["text"] == PAGE_TWO[3]
    assert tie_text.page_is_draft(scored) is False, "one doubtful line in five is checked, not a draft"


def test_two_lines_merged_by_the_reader_flag_the_pair():
    """source.align.known-misalignments-fixture: the reader read lines 1 and 2 as one; the pair is doubtful, the rest tie."""
    reads = [PAGE_ONE[0] + " " + PAGE_ONE[1], ""] + PAGE_ONE[2:]
    scored = tie_text.tie_lines(_text(PAGE_ONE), reads)

    assert [s["tied"] for s in scored][2:] == [True, True, True]
    assert not scored[1]["tied"], "the empty second half of a merge is never tied"


def test_two_reordered_lines_never_reorder_the_page_text():
    """source.align.known-misalignments-fixture: the reader swapped lines 2 and 3; the page text keeps its own order, and the swapped lines
    are doubtful rather than silently crossed."""
    reads = list(PAGE_ONE)
    reads[1], reads[2] = reads[2], reads[1]
    scored = tie_text.tie_lines(_text(PAGE_ONE), reads)

    assert " ".join(s["text"] for s in scored).split() == " ".join(PAGE_ONE).split(), "the page text is never reordered"
    assert not (scored[1]["tied"] and scored[2]["tied"]), "a swap is not tied as if it were right"


def test_a_page_aligned_too_poorly_is_a_draft():
    """source.align.below-threshold-stays-a-draft: most lines doubtful -> the page is a draft, not half-aligned."""
    garbled = ["xxxx", "", "qqqq zzzz", "", PAGE_TWO[4]]
    scored = tie_text.tie_lines(_text(PAGE_TWO), garbled)

    assert tie_text.page_is_draft(scored) is True
