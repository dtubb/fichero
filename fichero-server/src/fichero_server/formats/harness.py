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
# Ids a schema will accept
# ---------------------------------------------------------------------------


def xml_id(raw: str) -> str:
    """A value usable as `xs:ID` / `xs:IDREF`, derived from one of ours.

    **Found by exporting a real library page (#5084's second half).** Our ids are
    32-character hex, and roughly six in ten begin with a digit — which `xs:ID`
    refuses, because it is an `NCName` and an NCName may not start with a digit. The
    export failed on the id AND on every reference to it (`RegionRefIndexed/@regionRef`
    in PAGE XML, `TextLineID` in ALTO), so it has to be derived in ONE place and used
    on both sides of every reference.

    Deterministic: the same segment id always gives the same XML id, so a reference
    written in one part of the file matches the element written in another. Not
    reversible, and it does not need to be — the file's own ids exist to resolve
    references *inside the file*, and a re-import mints new ones.

    The hand-built pages in the format tests all happened to use ids like `r1` and
    `l1`, which are valid NCNames. **A constructed fixture cannot find this**: it is
    the fourth time a real artefact has caught what a made-up one could not.
    """
    if not raw:
        return "id"
    kept = [
        character if (character.isalnum() or character in "._-") else "_"
        for character in raw
    ]
    out = "".join(kept)
    first = out[0]
    if not (first.isalpha() or first == "_"):
        # A LETTER in front, not a digit stripped: keeping every character means two
        # ids that differ only in their first digit stay different.
        out = "id" + out
    return out


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
    #: Normalised `[x, y]`: a point shape (#4925). A ground control point's pixel end
    #: (IIIF Georeference `resourceCoords`).
    point: list[float] | None = None
    #: A world position as `(longitude, latitude)` in WGS 84 (EPSG:4326), GeoJSON's axis
    #: order: a ground control point's world end. WGS 84 because that is what Fichero
    #: stores (#5124) and the only CRS IIIF Georeference allows; a format in another CRS
    #: converts on read and says so, it does not put other numbers here.
    world: tuple[float, float] | None = None
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
    #: The page's size AS THE FILE STATES IT, in the file's own unit: `(width, height, unit)`,
    #: e.g. `(1003.0, 1469.0, "mm10")`. Kept for EVERY unit, because it is the only record of
    #: the page's proportions when there is no pixel grid (#5130: a `mm10` ALTO page was
    #: re-exported as a square 1000x1000 pixel page and every shape lost its aspect ratio).
    page_extent: tuple[float, float, str] | None = None
    #: The PAGE's own language, script and direction (#5085). A document states these
    #: (slice 9) and until now no writer could see them: `page_export` read them off
    #: SEGMENTS, so a page whose language is recorded once, at document level, reached
    #: no file at all.
    #:
    #: **Not the resolved cascade copied onto every line.** Writing a document's
    #: Spanish onto four hundred lines would store a DERIVED fact as a STATED one, and a
    #: re-import would read back a page whose every line independently declares Spanish
    #: — the `says-where-from` distinction destroyed by an export.
    language: str | None = None
    script: str | None = None
    direction: str | None = None
    segments: list[PageSegment] = field(default_factory=list)
    orders: list[PageOrder] = field(default_factory=list)
    #: A georeferencing pass's transformation, as the format states it:
    #: `{"type": "polynomial", "options": {"order": 1}}` or `{"type": "thinPlateSpline"}`.
    #: A property of the PASS (`source.geo.transformation-type`), so it lives on the page
    #: that becomes the pass. None when the file names none -- never a default, because
    #: "the file chose nothing" and "the file chose affine" are different facts.
    transformation: dict[str, Any] | None = None
    #: The DECLARED SIGNS this page's text uses (`source.sign.export-honest`, #4939): each
    #: `{"id", "name", "code_point", "list_references"}`. The text keeps the private-use
    #: character; this says what it means. Filled by the library export from the project's sign
    #: list; read back from TEI's `<charDecl>`.
    signs: list[dict[str, Any]] = field(default_factory=list)
    #: File-level content the model has no field for
    #: (`source.format.keeps-unrecognised`). Kept on the PAGE, which becomes the
    #: pass -- not on segments, because a format adds no field to segments and
    #: unrecognised content is usually about the file rather than one line.
    foreign: dict[str, Any] = field(default_factory=dict)


def pixel_grid(page: "SourcePage", report: "LossReport", fmt: str) -> tuple[int, int]:
    """The pixel grid a PIXEL-ONLY format writes against, and the loss said when it is invented.

    The recorded `image_size` when there is one. Otherwise a grid is INVENTED -- the formats
    that need pixels (PAGE, hOCR, TEI facsimile) cannot express "no grid" -- and it keeps the
    page's STATED PROPORTIONS (`page_extent`) at 1000 on the long side, falling back to a square
    only when the file stated no size at all. Before this each writer invented a square and a
    `mm10` ALTO page 1003 x 1469 came back 1000 x 1000: every shape stretched (#5130).
    """
    if page.image_size is not None:
        return page.image_size
    if page.page_extent is not None and page.page_extent[0] > 0 and page.page_extent[1] > 0:
        w, h, unit = page.page_extent
        scale = 1000.0 / max(w, h)
        grid = (max(1, round(w * scale)), max(1, round(h * scale)))
        report.note(
            "page size",
            1,
            f"the page states its size in {unit} ({w:g} x {h:g}) and no pixel grid, and {fmt} "
            f"needs pixels, so a {grid[0]}x{grid[1]} grid with the same proportions was written; "
            "the original pixel grid cannot be recovered",
        )
        return grid
    report.note(
        "page size",
        1,
        f"no page size was recorded at all, so {fmt}'s coordinates are against an invented "
        "1000x1000 page",
    )
    return (1000, 1000)


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
    #: For a format with no XSD but with normative rules (IIIF Georeference is JSON-LD
    #: and publishes prose, not a schema): a checker written from those rules, returning
    #: problems or []. `validate()` uses it where `schema` is None. A format with
    #: neither is unvalidatable by nature and must say so (test_export_validation.py).
    check: Callable[[bytes], list[str]] | None = None
    #: Whether the format can say what a declared sign MEANS (TEI's `<g>` + `<charDecl>`). A
    #: format that cannot still carries the character; `write_page` reports the rest as lost.
    carries_declared_signs: bool = False
    #: The extension an EXPORT of this format is named with. None: the first of `extensions`
    #: (hOCR `.hocr`, YOLO `.txt`). Set where the ecosystem names files more precisely than the
    #: sniffing extension does (a PAGE file is `x.page.xml`, not just `.xml`). The one source of
    #: an export's filename (`page_export.export_page`) -- no second table beside the registry.
    export_extension: str | None = None

    @property
    def file_extension(self) -> str:
        # "" for a format read only BESIDE its image, by stem (plain text, #5174): it names no
        # extension of its own, and indexing an empty tuple broke every page export.
        return self.export_extension or (self.extensions[0] if self.extensions else "")

    @property
    def reads(self) -> bool:
        return self.read is not None

    @property
    def writes(self) -> bool:
        return self.write is not None

    def schema_path(self) -> Path | None:
        return SCHEMA_DIR / self.schema if self.schema else None
