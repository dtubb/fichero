"""Interchange formats: the registry, validation, and the round-trip check (#4943).

`source.format.first-four` is DATA here, not a branch: PAGE XML, ALTO, TEI and YOLO
register themselves and the registry is the only thing that knows the list. Adding
a format adds a module and one `register()` call.
"""

from __future__ import annotations

from fichero_server.formats.harness import (
    FormatSpec,
    Loss,
    LossReport,
    PageOrder,
    PageSegment,
    SourcePage,
)

__all__ = [
    "FormatSpec",
    "Loss",
    "LossReport",
    "PageOrder",
    "PageSegment",
    "SourcePage",
    "UnknownFormat",
    "FormatCannotRead",
    "FormatCannotWrite",
    "InvalidExport",
    "known_formats",
    "register",
    "format_named",
    "format_for",
    "read_page",
    "write_page",
    "validate",
    "round_trip",
]

_REGISTRY: dict[str, FormatSpec] = {}


class UnknownFormat(ValueError):
    """Raised for a format name nothing registered. Names what there is, because a
    caller that asked for `page-xml` when the name is `pagexml` should not have to
    read the source."""

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(
            f"unknown interchange format {name!r}; this build has: "
            + ", ".join(sorted(_REGISTRY))
        )


class FormatCannotRead(ValueError):
    """Raised when a format registered a writer and no reader.

    A real state, not a bug: YOLO labels can be written for training and read back,
    but a format may legitimately go one way only. Saying so beats a `None` call.
    """

    def __init__(self, name: str) -> None:
        super().__init__(f"{name} can be written but not read by this build")


class FormatCannotWrite(ValueError):
    def __init__(self, name: str) -> None:
        super().__init__(f"{name} can be read but not written by this build")


class InvalidExport(ValueError):
    """Raised when a written export fails its own schema
    (`source.format.export-validated`).

    An invalid export is a REPORTED FAILURE and no file: a file that exists and
    does not validate is worse than no file, because somebody will send it to a
    colleague and the error will surface in their tool, about our data, a week
    later.
    """

    def __init__(self, name: str, problems: list[str]) -> None:
        self.name = name
        self.problems = problems
        super().__init__(
            f"the {name} export does not validate against its own schema: "
            + "; ".join(problems[:5])
            + (f" (and {len(problems) - 5} more)" if len(problems) > 5 else "")
        )


def register(spec: FormatSpec) -> FormatSpec:
    """Add a format. Idempotent by name so an import twice is not two formats."""
    _REGISTRY[spec.name] = spec
    return spec


def known_formats() -> list[FormatSpec]:
    return [_REGISTRY[name] for name in sorted(_REGISTRY)]


def format_named(name: str) -> FormatSpec:
    try:
        return _REGISTRY[name]
    except KeyError as exc:
        raise UnknownFormat(name) from exc


def format_for(filename: str, data: bytes | None = None) -> FormatSpec | None:
    """Which format a file is, or None.

    The extension NARROWS and the bytes DECIDE: PAGE XML, ALTO, hOCR and TEI are
    all `.xml`, and only the root element tells them apart. A harness that trusted
    the extension would import an ALTO file as PAGE XML and report the emptiness as
    the file's fault.
    """
    suffix = ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""
    candidates = [spec for spec in known_formats() if suffix in spec.extensions]
    if data is not None:
        for spec in candidates or known_formats():
            if spec.sniff is not None and spec.sniff(data):
                return spec
    if len(candidates) == 1:
        return candidates[0]
    return None


def read_page(name: str, data: bytes) -> SourcePage:
    spec = format_named(name)
    if spec.read is None:
        raise FormatCannotRead(name)
    return spec.read(data)


def write_page(name: str, page: SourcePage) -> tuple[bytes, LossReport]:
    """Write one page, validate it, and hand back the bytes with the loss report.

    Validation happens HERE rather than in each writer, which is the point of the
    harness: `source.format.export-validated` cannot be forgotten by the fifth
    format because no format implements it.
    """
    spec = format_named(name)
    if spec.write is None:
        raise FormatCannotWrite(name)
    report = LossReport(format=name)
    data = spec.write(page, report)
    problems = validate(spec, data)
    if problems:
        raise InvalidExport(name, problems)
    return data, report


def validate(spec: FormatSpec, data: bytes) -> list[str]:
    """Problems with these bytes against the format's own schema, or [].

    **An unvalidatable format returns [] and a format whose schema is MISSING
    raises**, because those are opposite facts: YOLO has no schema by nature, while
    a PAGE XML schema absent from the install is a broken build that would otherwise
    report every export as valid. This is the `[]`-means-two-things hazard, and the
    distinction is the whole reason `FormatSpec.schema` may be `None` explicitly.
    """
    if spec.schema is None:
        return []
    path = spec.schema_path()
    if path is None or not path.exists():
        raise FileNotFoundError(
            f"the schema for {spec.name} is not installed at {path} -- validation "
            "cannot pass vacuously, so this is a broken build rather than a valid "
            "export"
        )
    from fichero_server.formats.validation import validate_xml

    return validate_xml(data, path)


def _load_builtin_formats() -> None:
    """Import the shipped formats so they register themselves.

    Called at the bottom of this module so `from fichero_server.formats import
    known_formats` is enough -- a caller that had to import each format first would
    be a caller that can forget one, and `first-four` would stop being data.
    """
    from fichero_server.formats import alto, pagexml, tei  # noqa: F401


_load_builtin_formats()


# ---------------------------------------------------------------------------
# The round trip every format is held to
# ---------------------------------------------------------------------------


def round_trip(name: str, page: SourcePage) -> tuple[SourcePage, LossReport]:
    """Write `page`, read the bytes back, and hand over the pair.

    The acceptance test for every format (`source.format.round-trip-*`), and the
    comparison belongs to the CALLER because what may differ is format-specific —
    but the rules are the same everywhere and are worth stating once:

    * **ids are not compared.** A re-import mints new ones, and demanding stability
      would demand the format carry our uuids, which is asking it to be our
      database.
    * **positions are compared as SEQUENCE, not as numbers.** Slice 10's positions
      are spacing, not identity, and no format carries them.
    * **floats are compared to the precision the format declares.** PAGE XML writes
      integer pixels, so a normalised 0.3333 returns 0.3333 ± half a pixel;
      asserting equality would be asserting the format is lossless when it is not.
    * **the loss report's `what`s are subtracted, and nothing else is.** Anything
      missing that the report did not name is a failure.

    And the trap this helper cannot protect against, so it is named here: **a round
    trip passes if both directions share one mistake.** A writer that drops
    `direction` and a reader that supplies a default agree with each other
    perfectly. That is why the FIRST test of a format reads a file another tool
    wrote, and why the comparisons below assert against the MODEL's values rather
    than against what the other end of our own code produced.
    """
    data, report = write_page(name, page)
    return read_page(name, data), report
