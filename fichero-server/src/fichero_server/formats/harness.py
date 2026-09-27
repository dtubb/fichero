"""Source-model — the ONE interchange harness (#4943).

Spec: `formats-and-training.md`, "Rules for every format"; build notes:
`build-notes-formats-harness.md`.

`source.format.one-model-one-harness`: **every format reads INTO and writes OUT OF
the one source model, and adding a format adds a reader and a writer and no field
to segments.** Never a converter per pair — with five formats that is twenty
converters and twenty places for one fact to be mapped differently, which is the
shape that cost this programme six separate fixes in a day. PAGE XML to ALTO is
PAGE XML in, ALTO out, through the model, and if that loses something the loss
report says so.

WHAT IS IN HERE, and what deliberately is not. This module holds the harness: the
in-memory shape both directions speak (:class:`SourcePage`), what a format
registers (:class:`FormatSpec`), the loss report, schema validation, and the
round-trip check every format is held to. It holds **no format**, and it touches
**no database**: a reader turns bytes into a `SourcePage` and a writer turns a
`SourcePage` into bytes, so every format is testable from a fixture file with no
library at all — and no format can quietly learn a second way to write a segment.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol

#: Where the schemas live. ON DISK, versioned with Fichero
#: (`source.format.schemas-on-disk`): validation never goes to the network, and
#: neither does parsing -- an outside file is parsed with entities and network
#: access off, because a document that fetches a DTD is a document that can read
#: a researcher's filesystem.
SCHEMA_DIR = Path(__file__).parent / "schemas"


# ---------------------------------------------------------------------------
# The shape both directions speak
# ---------------------------------------------------------------------------


@dataclass
class PageSegment:
    """One segment as a format sees it.

    A FLAT record, not a `Segment` row: a reader has no database and must not need
    one, and a writer must not be able to reach a column nobody mapped. The fields
    are exactly what the formats between them can express -- adding one here is a
    claim that some format carries it.
    """

    #: `region`, `line`, `word`, `character` ... (`source.segment.open-kinds`).
    kind: str
    #: Normalised `[x, y, w, h]` on the page, or None when the format gave only a
    #: polygon (PAGE XML often does, and inventing a rect from it would be
    #: inventing a shape the file did not state).
    rect: list[float] | None = None
    #: Normalised `[[x, y], ...]`. PAGE XML `Coords`, Kraken's own shape.
    polygon: list[list[float]] | None = None
    #: Normalised `[[x, y], ...]`. PAGE XML `Baseline`; the thing Kraken and
    #: eScriptorium are built around.
    baseline: list[list[float]] | None = None
    #: The cascade's three facts (slice 9). PAGE XML and ALTO carry all three;
    #: `None` means the file said nothing, never a default.
    language: str | None = None
    script: str | None = None
    direction: str | None = None
    #: The readings, in the order the file gave them, each `(kind, text)`. Several
    #: are expressible (PAGE XML's indexed `TextEquiv`); WHICH ONE COUNTS is not,
    #: which is a loss and is reported rather than guessed.
    readings: list[tuple[str, str]] = field(default_factory=list)
    #: A reader's own id for this segment, used only to resolve the file's reading
    #: order. NEVER our id: a re-import mints new ones, and asking a format to
    #: carry our uuids would be asking it to be our database.
    ref: str | None = None
    #: Nesting, by `ref`: a line inside a region.
    parent_ref: str | None = None
    #: Anything the format stated that the model has no field for, kept verbatim
    #: (`source.format.keeps-unrecognised`).
    foreign: dict[str, Any] = field(default_factory=dict)


@dataclass
class PageOrder:
    """One named reading order as a format sees it (slice 10).

    PAGE XML has a `ReadingOrder` element and ALTO an order of its own, so this is
    not an invention: a round trip cannot be expressed without it, because export
    and re-import have to return the same sequence.
    """

    name: str
    #: Segment `ref`s, in sequence. Not positions: slice 10's positions are
    #: SPACING and not identity, and no format carries them.
    refs: list[str] = field(default_factory=list)
    kind: str = "as-written"


@dataclass
class SourcePage:
    """One page, as every format reads it and writes it.

    The only thing that crosses between a format and the model. A reader produces
    one; a writer consumes one; the database layer above turns one into a pass with
    its segments, orders and readings (`source.format.import-is-pass`).
    """

    #: What produced the file, for the pass's provenance. A name, never trusted as
    #: an actor: an imported file says who made it, and believing that would let a
    #: file claim a person's judgement.
    producer: str | None = None
    #: The image the coordinates are on, as the file names it. Needed to attach an
    #: import to the right rendition, and to say so when it cannot be matched.
    image_name: str | None = None
    #: Pixel size the file's coordinates are in, when it states one. Coordinates
    #: here are ALWAYS normalised; this is what they were normalised BY, so a
    #: writer can put integers back.
    image_size: tuple[int, int] | None = None
    segments: list[PageSegment] = field(default_factory=list)
    orders: list[PageOrder] = field(default_factory=list)
    #: File-level content the model has no field for
    #: (`source.format.keeps-unrecognised`). Kept on the PAGE, which becomes the
    #: pass -- not on segments, because a format adds no field to segments and
    #: unrecognised content is usually about the file rather than one line.
    foreign: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# The loss report
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Loss:
    """One thing a format could not carry."""

    #: What was lost, in the model's words (`reading choice`, `provenance`).
    what: str
    #: How many of them, so "one line's language" and "every line's language" are
    #: different reports.
    count: int
    #: Why the format cannot hold it. A reader of the report should not have to
    #: know the format to understand the sentence.
    why: str


@dataclass
class LossReport:
    """What an export could not carry (`source.format.loss-report`).

    A RECORD, not a log line, and part of the export's own output. **The round trip
    subtracts exactly what this names**, which makes honesty the acceptance
    criterion rather than completeness: a writer that drops something silently
    fails its round trip, and a writer that drops something and says so passes.
    That is the only way a format harness is ever finished -- no format carries
    everything, and pretending otherwise is how a silent loss ships.
    """

    format: str
    losses: list[Loss] = field(default_factory=list)

    def note(self, what: str, count: int, why: str) -> None:
        """Record a loss. Merges by `what`, so a writer can call it per segment
        without producing four hundred identical lines."""
        for existing in self.losses:
            if existing.what == what and existing.why == why:
                self.losses.remove(existing)
                self.losses.append(Loss(what, existing.count + count, why))
                return
        self.losses.append(Loss(what, count, why))

    @property
    def lost(self) -> set[str]:
        """The `what`s, for a round trip to subtract."""
        return {loss.what for loss in self.losses}

    def as_dict(self) -> dict[str, Any]:
        return {
            "format": self.format,
            "losses": [
                {"what": loss.what, "count": loss.count, "why": loss.why}
                for loss in self.losses
            ],
        }


# ---------------------------------------------------------------------------
# What a format registers
# ---------------------------------------------------------------------------


class Reader(Protocol):
    def __call__(self, data: bytes) -> SourcePage: ...


class Writer(Protocol):
    def __call__(self, page: SourcePage, report: LossReport) -> bytes: ...


@dataclass(frozen=True)
class FormatSpec:
    """One interchange format: a name, a reader, a writer, and its schema.

    `schema` is `None` for the formats that HAVE none (YOLO text labels are lines
    of numbers), which is stated rather than left absent -- an empty schema field
    and "this format cannot be validated" are different facts, and a harness that
    could not tell them apart would report every unvalidatable format as validated.
    """

    name: str
    #: Lower-case, with the dot: `.xml`, `.txt`. Several formats share `.xml`, so
    #: an extension narrows the candidates and never decides -- `sniff` does.
    extensions: tuple[str, ...]
    read: Reader | None = None
    write: Writer | None = None
    schema: str | None = None
    #: Whether export-then-import is expected to return the same page, less the
    #: loss report. False for a format that only goes one way.
    round_trips: bool = True
    #: Recognise this format from the file's own bytes. Extensions are a hint; a
    #: PAGE XML file and an ALTO file are both `.xml` and only their root element
    #: tells them apart.
    sniff: Callable[[bytes], bool] | None = None

    @property
    def reads(self) -> bool:
        return self.read is not None

    @property
    def writes(self) -> bool:
        return self.write is not None

    def schema_path(self) -> Path | None:
        return SCHEMA_DIR / self.schema if self.schema else None
