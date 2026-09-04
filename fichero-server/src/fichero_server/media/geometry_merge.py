"""Merge a reviewed transcription onto measured word boxes.

Two artifacts describe the same page and disagree. `regions` (Apple Vision)
carries MEASURED word and line boxes labelled with the text Vision thought it
read — on an early-modern hand, largely wrong. `transcription_review` carries
the CORRECT text and no geometry at all. So the page has accurate words with
no positions and accurate positions with inaccurate words, and a reader cannot
click a word in the transcript and see it on the image.

This is not a new geometry system. `OCRGeometryBox` already carries
`char_start`/`char_end`, so boxes are addressable by character range; the merge
is one string-to-string alignment that maps offsets in the reviewed text onto
offsets in the measured text.

Lines first, then words. Word-level matching against garbled OCR fails, but
line STRUCTURE is far more stable than line CONTENT: Vision produces roughly
the right number of lines in the right vertical order even where it reads
`mstruia` for `instruia`. Vertical order is monotonic, so alignments cannot
cross — a constraint strong enough to survive bad text. Inside a matched line
the search space collapses from the page to a dozen words.

Every emitted box records HOW it was obtained. Presenting an interpolated box
as a measured one is an unverified claim about where a word sits, and worse
than an absent box because it looks authoritative.

Design: agent-work/design/geometry-merge-review-to-word-boxes.md
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from fichero_server.media.ocr_geometry import (
    OCRGeometryBox,
    OCRGeometryLevel,
    OCRGeometryResult,
)

#: A line pairing scoring below this is not a pairing. Tuned against a Popayán
#: 1799 hand, where a correct pairing of a badly-read line still shares its
#: numerals, its proper nouns and its length.
MIN_LINE_SCORE = 0.30

#: Refuse when the reviewed text has more than this many lines per measured
#: line. A page where Vision merged two columns, or read a rúbrica as a line,
#: produces a wrong skeleton, and everything derived from it inherits the error
#: silently.
#:
#: Directional on purpose (measured 2026-09-03 on six Marshall diary pages).
#: The two imbalances are not the same defect. Reviewed ≫ measured means Vision
#: did not see most of the page, so the skeleton is missing — refuse. Measured
#: ≫ reviewed means Vision saw MORE than the transcript covers, which is the
#: ordinary case on a printed diary: the page carries preprinted furniture
#: (day headers, folio numbers, ruled-line fragments) that no transcript
#: transcribes. Those extra lines are unused candidates the monotonic
#: alignment simply skips, not evidence of a bad skeleton — and a symmetric
#: guard refused five of six real pages that align perfectly.
MAX_LINE_COUNT_RATIO = 2.5

#: Refuse when fewer than this fraction of reviewed lines found a partner.
MIN_LINE_COVERAGE = 0.5

#: A pairing at or above this similarity is STRONG evidence, not merely an
#: admissible one. `MIN_LINE_SCORE` is deliberately low so a badly-read line
#: can still find its own transcription; that tolerance is what a page of
#: short repetitive lines exploits.
MIN_STRONG_LINE_SCORE = 0.60

#: Refuse when fewer than this fraction of reviewed lines are STRONGLY paired.
#: With the count guard directional, this is what stands between a real
#: alignment and a plausible-looking accident. Measured: on a 1923 calendar
#: page — 40 numeric lines against 485 measured ones — 82% of lines found a
#: partner and the overlay was scattered nonsense, but only 25% of lines were
#: strongly paired. The five prose pages ran 78–100%.
MIN_STRONG_LINE_COVERAGE = 0.5

MEASURED = "measured"
DERIVED = "derived"

#: Provider prefix for geometry this module produced. A merged page is NOT an
#: OCR result: its text came from a person or a stronger model, its anchored
#: boxes were measured by the OCR engine named after the colon, and the rest
#: were interpolated between those anchors. Reporting it as the OCR provider
#: would let a backfilled page pass for a measured one, and the whole point of
#: recording provenance per box is that the two are not interchangeable.
ALIGNED_PROVIDER = "aligned"


def aligned_provider(measured_provider: str | None) -> str:
    """`aligned:<engine>` — names the alignment AND what it was aligned to."""
    engine = (measured_provider or "unknown").strip() or "unknown"
    if engine.startswith(f"{ALIGNED_PROVIDER}:"):
        return engine
    return f"{ALIGNED_PROVIDER}:{engine}"


@dataclass(slots=True)
class GeometryMergeOutcome:
    """The merge, or the reason there isn't one."""

    result: OCRGeometryResult | None = None
    refused: bool = False
    reason: str = ""
    #: Reviewed lines that found a measured partner.
    lines_matched: int = 0
    lines_total: int = 0
    #: Words placed on a real measured box vs interpolated inside a line.
    measured_words: int = 0
    derived_words: int = 0

    @property
    def coverage(self) -> float:
        return self.lines_matched / self.lines_total if self.lines_total else 0.0


@dataclass(slots=True)
class _Span:
    text: str
    start: int
    end: int
    key: str = field(default="")


def _normalize(text: str) -> str:
    """Fold to the part of a word that survives a bad reading.

    Accents, case and punctuation are exactly what an OCR pass gets wrong on a
    period hand, so comparing on them manufactures disagreement between a line
    and its own correct transcription.
    """
    decomposed = unicodedata.normalize("NFKD", text.lower())
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "", stripped)


def _line_spans(text: str) -> list[_Span]:
    spans: list[_Span] = []
    offset = 0
    for raw in text.split("\n"):
        stripped = raw.strip()
        if stripped:
            start = offset + raw.index(stripped) if stripped in raw else offset
            spans.append(
                _Span(stripped, start, start + len(stripped), _normalize(stripped))
            )
        offset += len(raw) + 1
    return spans


def _word_spans(line: _Span) -> list[_Span]:
    spans: list[_Span] = []
    for match in re.finditer(r"\S+", line.text):
        word = match.group()
        spans.append(
            _Span(
                word,
                line.start + match.start(),
                line.start + match.end(),
                _normalize(word),
            )
        )
    return spans


def _similarity(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    return SequenceMatcher(None, left, right).ratio()


def _measured_lines(measured: OCRGeometryResult) -> list[OCRGeometryBox]:
    """Line boxes, or lines synthesised from word boxes by vertical band.

    Some producers emit only words. Grouping those by their vertical centre
    recovers the line skeleton the alignment needs, and reading order within a
    band is left-to-right.
    """
    lines = [b for b in measured.boxes if b.level == OCRGeometryLevel.LINE]
    if lines:
        return sorted(lines, key=lambda b: (b.bbox[1], b.bbox[0]))

    words = [b for b in measured.boxes if b.level == OCRGeometryLevel.WORD]
    if not words:
        return []
    words = sorted(words, key=lambda b: (b.bbox[1], b.bbox[0]))
    bands: list[list[OCRGeometryBox]] = []
    for box in words:
        centre = box.bbox[1] + box.bbox[3] / 2
        placed = False
        for band in bands:
            head = band[0]
            if abs(centre - (head.bbox[1] + head.bbox[3] / 2)) <= head.bbox[3] * 0.6:
                band.append(box)
                placed = True
                break
        if not placed:
            bands.append([box])
    synthesised: list[OCRGeometryBox] = []
    for band in bands:
        band.sort(key=lambda b: b.bbox[0])
        x0 = min(b.bbox[0] for b in band)
        y0 = min(b.bbox[1] for b in band)
        x1 = max(b.bbox[0] + b.bbox[2] for b in band)
        y1 = max(b.bbox[1] + b.bbox[3] for b in band)
        synthesised.append(
            OCRGeometryBox(
                text=" ".join(b.text for b in band),
                bbox=[x0, y0, x1 - x0, y1 - y0],
                level=OCRGeometryLevel.LINE,
                page_index=band[0].page_index,
                metadata={"synthesised_from_words": len(band)},
            )
        )
    return sorted(synthesised, key=lambda b: (b.bbox[1], b.bbox[0]))


def _align_lines(
    reviewed: list[_Span],
    measured: list[OCRGeometryBox],
    *,
    min_score: float,
) -> list[int | None]:
    """Monotonic best alignment of reviewed lines onto measured line boxes.

    Order-preserving by construction: a page's lines run down the page in both
    readings, so an alignment that crossed would be wrong however well its text
    scored. That constraint is what keeps this honest where the text is not.
    """
    keys = [_normalize(box.text) for box in measured]
    rows, cols = len(reviewed), len(measured)
    dp = [[0.0] * (cols + 1) for _ in range(rows + 1)]
    back = [[""] * (cols + 1) for _ in range(rows + 1)]

    for i in range(1, rows + 1):
        for j in range(1, cols + 1):
            score = _similarity(reviewed[i - 1].key, keys[j - 1])
            diagonal = dp[i - 1][j - 1] + score if score >= min_score else -1.0
            skip_reviewed = dp[i - 1][j]
            skip_measured = dp[i][j - 1]
            best = max(diagonal, skip_reviewed, skip_measured)
            dp[i][j] = best
            back[i][j] = (
                "match" if best == diagonal
                else "up" if best == skip_reviewed
                else "left"
            )

    pairing: list[int | None] = [None] * rows
    i, j = rows, cols
    while i > 0 and j > 0:
        move = back[i][j]
        if move == "match":
            pairing[i - 1] = j - 1
            i -= 1
            j -= 1
        elif move == "up":
            i -= 1
        else:
            j -= 1
    return pairing


def _split_line_box(
    box: OCRGeometryBox, words: list[_Span]
) -> list[list[float]]:
    """Divide a line box across words in proportion to their character length.

    Proportional, not equal: a two-letter word and a twelve-letter word do not
    occupy the same width, and the whole point of a derived box is to be a
    plausible reading position rather than a uniform tick.
    """
    total = sum(max(len(w.text), 1) for w in words)
    x, y, width, height = box.bbox
    boxes: list[list[float]] = []
    cursor = x
    for word in words:
        share = width * (max(len(word.text), 1) / total)
        boxes.append([cursor, y, share, height])
        cursor += share
    return boxes


def merge_reviewed_text_onto_geometry(
    reviewed_text: str,
    measured: OCRGeometryResult,
    *,
    min_line_score: float = MIN_LINE_SCORE,
    max_line_count_ratio: float = MAX_LINE_COUNT_RATIO,
    min_line_coverage: float = MIN_LINE_COVERAGE,
    min_strong_line_score: float = MIN_STRONG_LINE_SCORE,
    min_strong_line_coverage: float = MIN_STRONG_LINE_COVERAGE,
) -> GeometryMergeOutcome:
    """Place the reviewed text's words on the measured page.

    Returns an outcome that either carries a geometry result whose text IS the
    reviewed text — so `char_start`/`char_end` index the corrected string, not
    the OCR's — or refuses and says why. Refusing is the correct answer when
    the measured skeleton cannot be trusted: a confident wrong overlay is worse
    than none, because nothing downstream can tell it apart from a right one.
    """
    reviewed_lines = _line_spans(reviewed_text)
    measured_lines = _measured_lines(measured)

    if not reviewed_lines:
        return GeometryMergeOutcome(refused=True, reason="reviewed text is empty")
    if not measured_lines:
        return GeometryMergeOutcome(
            refused=True, reason="measured geometry has no line or word boxes"
        )

    # Only the missing-skeleton direction is a defect: see MAX_LINE_COUNT_RATIO.
    ratio = len(reviewed_lines) / len(measured_lines)
    if ratio > max_line_count_ratio:
        return GeometryMergeOutcome(
            refused=True,
            lines_total=len(reviewed_lines),
            reason=(
                f"the reviewed text has {ratio:.1f}× more lines than the page "
                f"was measured to hold ({len(reviewed_lines)} reviewed vs "
                f"{len(measured_lines)} measured) — Vision did not see enough "
                "of this page for its line structure to be a skeleton"
            ),
        )

    pairing = _align_lines(reviewed_lines, measured_lines, min_score=min_line_score)
    matched = sum(1 for p in pairing if p is not None)
    coverage = matched / len(reviewed_lines)
    if coverage < min_line_coverage:
        return GeometryMergeOutcome(
            refused=True,
            lines_matched=matched,
            lines_total=len(reviewed_lines),
            reason=(
                f"only {matched} of {len(reviewed_lines)} reviewed lines found a "
                f"measured partner ({coverage:.0%}); below the "
                f"{min_line_coverage:.0%} floor this is a failed alignment, not "
                "a partial one"
            ),
        )

    # Coverage alone counts pairings; it cannot tell a pairing that is evidenced
    # from one the low `min_line_score` floor let through. A page of short
    # repetitive lines (a printed calendar's numerals) fills its coverage with
    # weak matches and produces a scattered overlay that every downstream
    # consumer would read as authoritative.
    strong = sum(
        1
        for index, partner in enumerate(pairing)
        if partner is not None
        and _similarity(
            reviewed_lines[index].key, _normalize(measured_lines[partner].text)
        )
        >= min_strong_line_score
    )
    strong_coverage = strong / len(reviewed_lines)
    if strong_coverage < min_strong_line_coverage:
        return GeometryMergeOutcome(
            refused=True,
            lines_matched=matched,
            lines_total=len(reviewed_lines),
            reason=(
                f"only {strong} of {len(reviewed_lines)} reviewed lines matched "
                f"their measured partner strongly ({strong_coverage:.0%} at or "
                f"above {min_strong_line_score:.2f} similarity); the "
                f"{matched} pairings this page found are weak enough to be "
                "coincidence, not an alignment"
            ),
        )

    word_boxes = sorted(
        (b for b in measured.boxes if b.level == OCRGeometryLevel.WORD),
        key=lambda b: (b.bbox[1], b.bbox[0]),
    )
    boxes: list[OCRGeometryBox] = []
    measured_count = 0
    derived_count = 0

    for line_index, line in enumerate(reviewed_lines):
        partner_index = pairing[line_index]
        if partner_index is None:
            # No anchor at all: emitting a box here would be a guess about a
            # line we could not locate. The design calls that `unknown`, and
            # `unknown` means no box.
            continue
        line_box = measured_lines[partner_index]
        words = _word_spans(line)
        if not words:
            continue

        # Word boxes that fall inside this line's band, in reading order.
        inside = [
            b for b in word_boxes
            if line_box.bbox[1] - 1e-6
            <= b.bbox[1] + b.bbox[3] / 2
            <= line_box.bbox[1] + line_box.bbox[3] + 1e-6
        ]
        placed: dict[int, OCRGeometryBox] = {}
        if inside:
            matcher = SequenceMatcher(
                None,
                [w.key for w in words],
                [_normalize(b.text) for b in inside],
            )
            for a, b, size in matcher.get_matching_blocks():
                for offset in range(size):
                    placed[a + offset] = inside[b + offset]

        fallback = _split_line_box(line_box, words)
        for index, word in enumerate(words):
            anchor = placed.get(index)
            if anchor is not None:
                bbox = list(anchor.bbox)
                provenance = MEASURED
                measured_count += 1
            else:
                bbox = fallback[index]
                provenance = DERIVED
                derived_count += 1
            boxes.append(
                OCRGeometryBox(
                    text=word.text,
                    bbox=bbox,
                    level=OCRGeometryLevel.WORD,
                    char_start=word.start,
                    char_end=word.end,
                    page_index=line_box.page_index,
                    provider=aligned_provider(measured.provider),
                    source="geometry_merge",
                    metadata={
                        "provenance": provenance,
                        "line_index": line_index,
                        "measured_line_index": partner_index,
                    },
                )
            )

    result = OCRGeometryResult(
        text=reviewed_text,
        provider=aligned_provider(measured.provider),
        model=measured.model,
        boxes=boxes,
        source="geometry_merge",
        rendition_id=measured.rendition_id,
        metadata={
            "merge": {
                "lines_matched": matched,
                "lines_total": len(reviewed_lines),
                "measured_words": measured_count,
                "derived_words": derived_count,
                "measured_line_count": len(measured_lines),
            }
        },
    )
    return GeometryMergeOutcome(
        result=result,
        lines_matched=matched,
        lines_total=len(reviewed_lines),
        measured_words=measured_count,
        derived_words=derived_count,
    )
