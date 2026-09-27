"""XML parsing and validation for the interchange harness (#4943).

`source.format.schemas-on-disk`: **validation never goes to the network, and
neither does parsing.** An outside file is parsed with entities and network access
OFF — a document that fetches a DTD is a document that can read a researcher's
filesystem, and an archival tool is exactly the kind of program people point at
files they did not write.
"""

from __future__ import annotations

import os
import tempfile
import threading
from contextlib import contextmanager
from functools import lru_cache
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


#: Absolute schema URLs a vendored schema IMPORTS, mapped to the local file that
#: satisfies them. ALTO's XSD imports xlink by absolute URL, so validating it with
#: the network off fails at schema-parse time unless the import resolves locally —
#: which is `source.format.schemas-on-disk` reaching one level deeper than the
#: schema itself.
#:
#: A WHITELIST, and anything outside it RAISES rather than being fetched or
#: ignored. Ignoring an unresolved import would leave a schema silently missing
#: half its definitions, which is validation passing vacuously again; fetching it
#: would put the network back in the path.
VENDORED_IMPORTS: dict[str, str] = {
    # The XML namespace's own schema, which xlink's imports. Correct and vendored.
    "http://www.w3.org/2001/xml.xsd": "xml.xsd",
    "https://www.w3.org/2001/xml.xsd": "xml.xsd",
    # LOC's METS XLink schema v2 (Nov 2004), which ALTO's XSD imports by this URL. It
    # defines `simpleLink`, which ALTO references. W3C's modern `xlink.xsd` is NOT a
    # substitute -- it defines `simpleAttrs` instead, and mapping it here built a schema
    # missing the definitions ALTO uses (libxml2 refused, correctly). `loc.gov` returns 403 to
    # a script, so the vendored copy is OCR-D/core's `xlink.xsd` (see schemas/PROVENANCE.md).
    "http://www.loc.gov/standards/xlink/xlink.xsd": "xlink.xsd",
}


class UnvendoredSchemaImport(RuntimeError):
    """A schema imports something we do not ship.

    Loud on purpose: the alternative is a schema parsed without part of itself,
    which validates everything it can no longer see.
    """

    def __init__(self, url: str) -> None:
        self.url = url
        super().__init__(
            f"a vendored schema imports {url!r}, which is not in VENDORED_IMPORTS. "
            "Validation never goes to the network, and a schema missing an import "
            "would validate vacuously — vendor the file and add it to the map."
        )


class _LocalOnlyResolver:
    """Resolve a schema's imports from disk, and refuse everything else."""

    def __init__(self, schema_dir: Path) -> None:
        self._dir = schema_dir

    def resolve(self, url: str, _public_id: str, context: Any) -> Any:  # noqa: D401
        local = VENDORED_IMPORTS.get(url)
        if local is None:
            raise UnvendoredSchemaImport(url)
        # `resolve_string` rather than `resolve_filename`: the bytes are handed
        # straight to libxml2, so nothing re-opens a path and nothing can fall back
        # to the URL we just refused to fetch.
        return context.resolve_string(
            (self._dir / local).read_bytes(), context, base_url=str(self._dir) + "/"
        )


@lru_cache(maxsize=8)
def _offline_schema(schema_path: Path) -> Path:
    """A copy of the schema GRAPH whose imports point at neighbouring files.

    **Why this exists, after three simpler attempts failed.** A schema's imports are
    resolved by libxml2 itself, not by Python, so with the network off an
    `<xsd:import schemaLocation="http://...">` fails. An lxml `Resolver` is not
    consulted at schema-build time; rewriting only the TOP-level import fixed one
    level and left xlink's own import of the XML namespace reaching out; an XML
    catalog was not picked up either.

    So the whole graph is materialised once into a temporary directory with every
    absolute import rewritten to the file beside it -- which is the only approach
    that works at EVERY level, including levels we have not met.

    The vendored files are never modified (`schemas/PROVENANCE.md`: a schema edited
    to suit us no longer says what the format is). These are copies, made at
    validation time, in a directory the process owns.

    An absolute import with no vendored file RAISES. It is not fetched and it is not
    dropped: a schema missing part of itself validates everything it can no longer
    see, which is the vacuous pass one level deeper than a missing schema file.
    """
    from lxml import etree

    target = Path(tempfile.mkdtemp(prefix="fichero-schemas-")) 
    pending = [schema_path]
    written: set[str] = set()
    while pending:
        source = pending.pop()
        if source.name in written:
            continue
        tree = etree.parse(str(source), parser=safe_parser())
        for node in tree.iter("{http://www.w3.org/2001/XMLSchema}import"):
            location = node.get("schemaLocation")
            if not location:
                continue
            if location.startswith(("http://", "https://")):
                local = VENDORED_IMPORTS.get(location)
                if local is None:
                    raise UnvendoredSchemaImport(location)
            else:
                local = location
            node.set("schemaLocation", local)
            pending.append(schema_path.parent / local)
        tree.write(str(target / source.name), xml_declaration=True, encoding="UTF-8")
        written.add(source.name)
    return target / schema_path.name


@contextmanager
def _catalog(schema_dir: Path) -> Any:
    """Point libxml2 at the vendored XML catalog for the length of one validation.

    The in-memory import rewrite below fixes the TOP level; a catalog fixes EVERY
    level, which matters because xlink's own schema imports the XML namespace's and
    nothing we rewrite reaches that. libxml2 reads `XML_CATALOG_FILES` from the
    environment, so it is set here and restored afterwards rather than left on the
    process -- a global that changes how every other XML read behaves would be a
    side effect nobody expects from validating an export.
    """
    catalog = schema_dir / "catalog.xml"
    previous = os.environ.get("XML_CATALOG_FILES")
    if catalog.exists():
        os.environ["XML_CATALOG_FILES"] = str(catalog)
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("XML_CATALOG_FILES", None)
        else:
            os.environ["XML_CATALOG_FILES"] = previous


def _schema_tree(schema_path: Path) -> Any:
    """The schema, with its absolute imports POINTED AT THE VENDORED FILES.

    `lxml` builds an `XMLSchema` through libxml2, which resolves an
    `<xsd:import schemaLocation="http://...">` itself and does not consult a Python
    resolver reliably at schema-build time. So the location is rewritten IN MEMORY
    to the neighbouring vendored file, and the tree keeps the schema's own path as
    its base URL so the relative name resolves on disk.

    **The file on disk is never modified** -- the rule in `schemas/PROVENANCE.md` is
    that a schema edited to suit us no longer says what the format is. This rewrites
    the parsed copy, for the length of one validation.

    An absolute import that is NOT vendored raises. Ignoring it would leave the
    schema missing part of itself and validating everything it can no longer see,
    which is the vacuous-pass shape one level deeper than a missing schema file.
    """
    from lxml import etree

    tree = etree.parse(str(schema_path), parser=safe_parser())
    for node in tree.iter("{http://www.w3.org/2001/XMLSchema}import"):
        location = node.get("schemaLocation")
        if not location or not location.startswith(("http://", "https://")):
            continue
        local = VENDORED_IMPORTS.get(location)
        if local is None:
            raise UnvendoredSchemaImport(location)
        node.set("schemaLocation", local)
    return tree


def _schema_parser(schema_dir: Path) -> Any:
    from lxml import etree

    parser = safe_parser()
    resolver = _LocalOnlyResolver(schema_dir)

    class _Resolver(etree.Resolver):
        def resolve(self, system_url, public_id, context):
            if system_url and system_url.startswith(("http://", "https://")):
                return resolver.resolve(system_url, public_id, context)
            return None

    parser.resolvers.add(_Resolver())
    return parser


def parse_html(data: bytes) -> Any:
    """Parse outside HTML safely, for the formats that ARE HTML rather than XML.

    hOCR is a microformat over HTML, so the XML parser is the wrong tool: real
    engine output has unclosed `<meta>` tags and `<br>`s, and XHTML-shaped output
    parses either way. **My own writer produced the file that proved it** -- it emits
    HTML, the reader read XML, and the round trip failed on an unclosed `meta`.

    Same safety posture as `safe_parser`: no network, no DTD loading, no entity
    resolution. An archival tool is pointed at files nobody vetted.
    """
    from lxml import etree

    parser = etree.HTMLParser(no_network=True, huge_tree=False)
    tree = etree.fromstring(data, parser=parser)
    if tree is None:
        raise ValueError("not parseable as HTML")
    return tree


def validate_xml(data: bytes, schema_path: Path) -> list[str]:
    """Problems with these bytes against an XSD on disk, or [].

    Returns the schema's own messages rather than a boolean: "does not validate" is
    not actionable, and the person reading it is usually the person who wrote the
    writer.
    """
    from lxml import etree

    # BOTH improvements, composed: `_offline_schema` materialises the import graph with
    # absolute locations rewritten (ALTO imports xlink by URL and the network is off), and
    # `_compiled` caches the compiled form per process (TEI's `tei_all` took ~7 s each time).
    # Compile-cache the MATERIALISED path, not the original -- caching the original would
    # recompile ALTO's graph on every export, and materialising without caching would pay
    # TEI's seven seconds forever.
    schema = _compiled(str(_offline_schema(schema_path)))
    try:
        tree = etree.fromstring(data, parser=safe_parser())
    except etree.XMLSyntaxError as exc:
        return [f"not well-formed XML: {exc}"]
    with _VALIDATE_LOCK:  # a compiled schema keeps its error log; one validation at a time
        if schema.validate(tree):
            return []
        return [f"line {entry.line}: {entry.message}" for entry in schema.error_log]


_VALIDATE_LOCK = threading.Lock()


@lru_cache(maxsize=8)
def _compiled(path: str) -> Any:
    """The schema, compiled ONCE per process. TEI's `tei_all.xsd` is 1 MB and compiling it took
    seconds on every export; the file on disk never changes under a running engine, so the
    compiled form is cached by path."""
    from lxml import etree

    with open(path, "rb") as handle:
        return etree.XMLSchema(etree.parse(handle, parser=safe_parser()))
