"""YOLO text labels, in and out (#4944).

Spec: `formats-and-training.md` (`source.format.yolo-in`, `.yolo-out`,
`.round-trip-yolo`); build notes: `build-notes-formats-harness.md`.

One line per box: `class cx cy w h`, all four numbers **normalised 0–1**, centre
first. That is the whole format — no text, no language, no order, no nesting, no
identity.

**So YOLO is the loss report's hardest case, and the most useful one.** Every other
format loses details; YOLO loses almost everything a source model is FOR. If the
design is right, that makes YOLO's writer honest rather than impossible: it carries
the shapes, declares the rest, and the round trip subtracts exactly what it declared.
If the design were wrong, YOLO would be the format that forced a fudge.

Two things fall out of that:

* **The round trip is about SHAPES.** `round_trips=True` is meaningful for geometry
  and only for geometry, which the report says in full.
* **Identity cannot survive.** A YOLO file has no ids, so a re-import mints new ones
  and the comparison is by sequence and position — the same rule that already applies
  to every format, made unavoidable here.

Coordinates are already normalised, so YOLO needs no page size — the one respect in
which it is easier than PAGE XML and ALTO.
"""

from __future__ import annotations

from fichero_server.formats import register
from fichero_server.formats.harness import (
    FormatSpec,
    LossReport,
    PageSegment,
    SourcePage,
)

#: Which class number means which granularity. A YOLO file is meaningless without
#: this mapping, and it lives WITH the format rather than in a configuration file
#: nobody versions: a training set whose class 0 means "line" in one export and
#: "region" in another is a training set that teaches nothing.
CLASS_KINDS: dict[int, str] = {0: "region", 1: "line", 2: "word", 3: "character"}
KIND_CLASSES: dict[str, int] = {kind: number for number, kind in CLASS_KINDS.items()}


class MalformedYoloLine(ValueError):
    """Raised for a line that is not `class cx cy w h`.

    Refused rather than skipped: a training set with silently dropped boxes trains
    a model to miss exactly those, and nothing downstream would ever say so.
    """

    def __init__(self, line_number: int, text: str) -> None:
        self.line_number = line_number
        super().__init__(
            f"line {line_number} is not `class cx cy w h`: {text!r}. Refusing rather "
            "than skipping -- a training set with boxes quietly missing teaches a "
            "model to miss them."
        )


def _sniff(data: bytes) -> bool:
    """YOLO by its shape: every non-empty line is five numbers.

    There is no header, no namespace and no marker, so the only honest test is
    whether the content IS the format. Deliberately strict: one line of prose means
    this is not a YOLO label file, and guessing would turn a text file into boxes.
    """
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return False
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return False
    for line in lines[:20]:
        parts = line.split()
        if len(parts) != 5:
            return False
        try:
            int(parts[0])
            [float(value) for value in parts[1:]]
        except ValueError:
            return False
    return True


def read(data: bytes) -> SourcePage:
    """One YOLO label file as the model would have stored it: shapes, and nothing else."""
    page = SourcePage(producer="yolo")
    for number, line in enumerate(data.decode("utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        parts = line.split()
        if len(parts) != 5:
            raise MalformedYoloLine(number, line)
        try:
            class_number = int(parts[0])
            cx, cy, w, h = (float(value) for value in parts[1:])
        except ValueError as exc:
            raise MalformedYoloLine(number, line) from exc
        page.segments.append(
            PageSegment(
                kind=CLASS_KINDS.get(class_number, "region"),
                # Centre-first to top-left: the one conversion this format needs, and
                # the one a naive reader gets wrong by half a box.
                rect=[cx - w / 2, cy - h / 2, w, h],
                polygon=[
                    [cx - w / 2, cy - h / 2], [cx + w / 2, cy - h / 2],
                    [cx + w / 2, cy + h / 2], [cx - w / 2, cy + h / 2],
                ],
                foreign={"yolo:class": class_number},
            )
        )
    return page


def write(page: SourcePage, report: LossReport) -> bytes:
    """One page as YOLO labels, declaring everything the format cannot hold.

    The report is long by design. A format that carries four numbers per box and
    nothing else should produce a long report, and a short one would mean the writer
    was not looking.
    """
    lines: list[str] = []
    text_count = 0
    language_count = 0
    script_count = 0

    for segment in page.segments:
        rect = segment.rect or _bounds(segment.polygon)
        if rect is None:
            report.note(
                "segments with no rectangle",
                1,
                "YOLO is four numbers per box, so a segment with no shape has nothing "
                "to write",
            )
            continue
        class_number = KIND_CLASSES.get(segment.kind)
        if class_number is None:
            report.note(
                f"{segment.kind} segments",
                1,
                "YOLO's class numbers cover region, line, word and character; this "
                "granularity has no number",
            )
            continue
        x, y, w, h = rect
        lines.append(
            f"{class_number} {x + w / 2:.6f} {y + h / 2:.6f} {w:.6f} {h:.6f}"
        )
        if segment.readings:
            text_count += 1
        if segment.language:
            language_count += 1
        if segment.script:
            script_count += 1

    if text_count:
        report.note(
            "the text of every segment",
            text_count,
            "YOLO labels hold geometry only: there is nowhere in the format for a "
            "transcription, which is the point of it (it trains a detector, not a "
            "reader)",
        )
    if language_count:
        report.note(
            "language",
            language_count,
            "YOLO has no field for language",
        )
    if script_count:
        report.note("script", script_count, "YOLO has no field for script")
    if page.orders:
        report.note(
            "named reading orders",
            len(page.orders),
            "YOLO has no order: its lines are a set of boxes, and their sequence in "
            "the file carries no meaning",
        )
    if any(segment.parent_ref for segment in page.segments):
        report.note(
            "nesting",
            sum(1 for s in page.segments if s.parent_ref),
            "YOLO boxes are flat: a line inside a region is two unrelated boxes",
        )
    if any(segment.ref for segment in page.segments):
        report.note(
            "segment identity",
            sum(1 for s in page.segments if s.ref),
            "YOLO has no ids, so nothing connects a box to the segment it came from "
            "and a re-import mints new ones",
        )

    return ("\n".join(lines) + "\n").encode("utf-8")


def _bounds(polygon: list[list[float]] | None) -> list[float] | None:
    if not polygon:
        return None
    xs = [p[0] for p in polygon]
    ys = [p[1] for p in polygon]
    return [min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)]


register(
    FormatSpec(
        name="yolo",
        extensions=(".txt",),
        read=read,
        write=write,
        # No schema, by nature: the format is five numbers a line. The same honest
        # `None` hOCR uses, for the same reason.
        schema=None,
        # True, and it means SHAPES: everything else is in the loss report, and the
        # round trip subtracts exactly that.
        round_trips=True,
        sniff=_sniff,
    )
)
