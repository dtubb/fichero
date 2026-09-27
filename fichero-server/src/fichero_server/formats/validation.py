"""XML parsing and validation for the interchange harness (#4943).

`source.format.schemas-on-disk`: **validation never goes to the network, and
neither does parsing.** An outside file is parsed with entities and network access
OFF — a document that fetches a DTD is a document that can read a researcher's
filesystem, and an archival tool is exactly the kind of program people point at
files they did not write.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def safe_parser() -> Any:
    """An `lxml` parser with entities, DTD loading and network access off.

    One place, so no reader can construct its own and be the one that forgets.
    """
    from lxml import etree

    return etree.XMLParser(
        resolve_entities=False,
        no_network=True,
        load_dtd=False,
        dtd_validation=False,
        huge_tree=False,
    )


def parse(data: bytes) -> Any:
    """Parse outside XML safely, or raise `lxml`'s own error.

    Raises rather than returning None: "this is not XML" and "this is XML with
    nothing in it" are different facts and a caller must be able to tell them
    apart.
    """
    from lxml import etree

    return etree.fromstring(data, parser=safe_parser())


def validate_xml(data: bytes, schema_path: Path) -> list[str]:
    """Problems with these bytes against an XSD on disk, or [].

    Returns the schema's own messages rather than a boolean: "does not validate" is
    not actionable, and the person reading it is usually the person who wrote the
    writer.
    """
    from lxml import etree

    with schema_path.open("rb") as handle:
        schema = etree.XMLSchema(etree.parse(handle, parser=safe_parser()))
    try:
        tree = etree.fromstring(data, parser=safe_parser())
    except etree.XMLSyntaxError as exc:
        return [f"not well-formed XML: {exc}"]
    if schema.validate(tree):
        return []
    return [f"line {entry.line}: {entry.message}" for entry in schema.error_log]
