"""Safe XML helpers for importer surfaces."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import IO, Any

try:
    from defusedxml import ElementTree as SafeET
except ImportError:  # pragma: no cover - exercised when dependency is absent locally
    from xml.etree import ElementTree as SafeET  # type: ignore[assignment]


_FORBIDDEN_XML_MARKERS = (b"<!DOCTYPE", b"<!ENTITY")


def reject_xml_entities(data: bytes) -> None:
    """Reject XML entity declarations before any parser can expand them."""

    upper = data[:4096].upper()
    if any(marker in upper for marker in _FORBIDDEN_XML_MARKERS):
        raise ValueError("XML entity declarations are not allowed")


def parse_xml(source: str | Path | IO[bytes] | IO[str]) -> Any:
    """Parse XML with defusedxml when available and a DOCTYPE fallback check."""

    if isinstance(source, (str, Path)):
        reject_xml_entities(Path(source).read_bytes())
    else:
        pos = source.tell()
        sample = source.read(4096)
        if isinstance(sample, str):
            sample = sample.encode("utf-8", errors="ignore")
        reject_xml_entities(sample)
        source.seek(pos)
    return SafeET.parse(source)


def iterparse_xml(
    source: str | Path | IO[bytes] | IO[str],
    *,
    events: Iterable[str] | None = None,
) -> Iterator[tuple[str, Any]]:
    """Iterparse XML with entity rejection before streaming starts."""

    if isinstance(source, (str, Path)):
        reject_xml_entities(Path(source).read_bytes())
    else:
        pos = source.tell()
        sample = source.read(4096)
        if isinstance(sample, str):
            sample = sample.encode("utf-8", errors="ignore")
        reject_xml_entities(sample)
        source.seek(pos)
    return SafeET.iterparse(source, events=events)


def parse_xml_string(text: str) -> Any:
    """Parse an in-memory XML string through the same entity rejection +
    defused parser as ``parse_xml`` — the chokepoint for well-formedness
    checks on model-generated markup (#4329)."""

    reject_xml_entities(text[:4096].encode("utf-8", errors="ignore"))
    return SafeET.fromstring(text)
