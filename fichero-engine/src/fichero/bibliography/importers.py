"""Bibliography file importers + exporter (#909).

Round-trip with reference managers (Zotero / Mendeley / EndNote):
- BibTeX (.bib) — the lingua franca
- RIS (.ris) — older format, EndNote / RefWorks default
- CSL JSON — Zotero's preferred export

Each parser returns SourceMetadata-shaped dicts so callers can pass
them into existing extractor / merge / citation-render flows.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# =============================================================================
# BibTeX parser (hand-rolled — no bibtexparser dep)
# =============================================================================


_BIBTEX_FIELD_RE = re.compile(
    r"(\w+)\s*=\s*[{\"]([^{}]*(?:\{[^{}]*\}[^{}]*)*)[}\"]\s*,?",
    re.DOTALL,
)
_BIBTEX_ENTRY_RE = re.compile(r"@(\w+)\s*\{([^,]+),(.*?)\n\s*\}\s*(?=@|\Z)", re.DOTALL)


def _bibtex_unescape(text: str) -> str:
    """Reverse the BibTeX escape conventions for storage."""
    return (
        text.replace(r"\&", "&")
            .replace(r"\%", "%")
            .replace(r"\$", "$")
            .replace(r"\#", "#")
            .replace(r"\_", "_")
            .replace(r"\{", "{")
            .replace(r"\}", "}")
            .replace(r"\\", "\\")
            .strip()
    )


def _parse_bibtex_authors(value: str) -> list[str]:
    """BibTeX uses ' and ' (lowercase) to separate authors."""
    return [a.strip() for a in re.split(r"\s+and\s+", value) if a.strip()]


def _iter_bibtex_entries(text: str) -> list[tuple[str, str, dict[str, str]]]:
    entries: list[tuple[str, str, dict[str, str]]] = []
    for match in _BIBTEX_ENTRY_RE.finditer(text):
        entry_type = match.group(1).lower()
        cite_key = match.group(2).strip()
        body = match.group(3)
        fields: dict[str, str] = {}
        for field_match in _BIBTEX_FIELD_RE.finditer(body):
            name = field_match.group(1).strip().lower()
            value = _bibtex_unescape(field_match.group(2))
            fields[name] = value
        entries.append((entry_type, cite_key, fields))
    return entries


def read_bibtex(text: str) -> list[dict[str, Any]]:
    """Parse a BibTeX string into a list of SourceMetadata dicts.

    Hand-rolled — covers the 95% common cases:
    - @book / @article / @misc / @inbook / @incollection
    - {curly} and "quoted" values
    - "Author, First and Other, Second" joiner

    Skips entries that don't look like a valid @type{key, ...} block.
    """
    entries: list[dict[str, Any]] = []
    for entry_type, cite_key, fields in _iter_bibtex_entries(text):
        out: dict[str, Any] = {}
        if "title" in fields:
            out["title"] = fields["title"]
        if "author" in fields:
            out["authors"] = _parse_bibtex_authors(fields["author"])
        if "year" in fields:
            out["date"] = fields["year"]
        for k in ("publisher", "journal", "volume", "pages", "doi", "isbn", "issn", "url", "language"):
            if k in fields:
                if k == "isbn":
                    isbn_clean = re.sub(r"[^0-9X]", "", fields[k].upper())
                    if len(isbn_clean) == 13:
                        out["isbn_13"] = isbn_clean
                    elif len(isbn_clean) == 10:
                        out["isbn_10"] = isbn_clean
                else:
                    out[k] = fields[k]
        if "note" in fields:
            out["notes"] = fields["note"]
        if "number" in fields:
            out["issue"] = fields["number"]
        metadata = out.setdefault("metadata", {})
        if "file" in fields:
            metadata["filename"] = Path(fields["file"]).name
        metadata["bibtex_entry_type"] = entry_type
        metadata["bibtex_cite_key"] = cite_key
        extra_fields = {
            key: value
            for key, value in fields.items()
            if key
            not in {
                "author",
                "title",
                "year",
                "publisher",
                "journal",
                "volume",
                "pages",
                "doi",
                "isbn",
                "issn",
                "url",
                "language",
                "number",
                "file",
                "note",
            }
        }
        if extra_fields:
            metadata["bibtex_fields"] = extra_fields
        out["bibtex"] = write_bibtex([out])
        entries.append(out)
    return entries


# =============================================================================
# RIS parser (EndNote / RefWorks)
# =============================================================================


# RIS is line-oriented: ``TY  - BOOK``, ``AU  - Smith, Bob``, ending with ``ER  -``.
_RIS_TAG_TO_FIELD = {
    "TI": "title", "T1": "title",
    "AU": "_author_append",
    "A1": "_author_append",
    "PY": "_year",
    "Y1": "_year",
    "DA": "date",
    "PB": "publisher",
    "JO": "journal", "JF": "journal", "T2": "journal",
    "VL": "volume",
    "IS": "issue",
    "SP": "_pages_start",
    "EP": "_pages_end",
    "DO": "doi",
    "SN": "_isbn",
    "UR": "url",
    "LA": "language",
}


def read_ris(text: str) -> list[dict[str, Any]]:
    """Parse a RIS string into a list of SourceMetadata dicts."""
    entries: list[dict[str, Any]] = []
    current: dict[str, Any] = {}
    authors: list[str] = []
    page_start: str | None = None
    page_end: str | None = None
    year: str | None = None
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if not line:
            continue
        if line.startswith("ER"):
            if authors:
                current["authors"] = authors
            if page_start or page_end:
                current["pages"] = f"{page_start or ''}-{page_end or ''}".strip("-")
            if year and "date" not in current:
                current["date"] = year
            current["bibtex"] = write_bibtex([current])
            entries.append(current)
            current, authors, page_start, page_end, year = {}, [], None, None, None
            continue
        if len(line) < 6 or "  - " not in line:
            continue
        tag, value = line[:2], line[6:].strip()
        field = _RIS_TAG_TO_FIELD.get(tag)
        if field is None:
            continue
        if field == "_author_append":
            authors.append(value)
        elif field == "_year":
            year = re.search(r"\b(\d{4})\b", value).group(1) if re.search(r"\b(\d{4})\b", value) else value
        elif field == "_pages_start":
            page_start = value
        elif field == "_pages_end":
            page_end = value
        elif field == "_isbn":
            isbn_clean = re.sub(r"[^0-9X]", "", value.upper())
            if len(isbn_clean) == 13:
                current["isbn_13"] = isbn_clean
            elif len(isbn_clean) == 10:
                current["isbn_10"] = isbn_clean
        else:
            current[field] = value
    return entries


# =============================================================================
# CSL JSON (Zotero export)
# =============================================================================


def read_csl_json(text: str) -> list[dict[str, Any]]:
    """Parse Zotero's CSL JSON export."""
    try:
        records = json.loads(text)
    except json.JSONDecodeError as exc:
        logger.warning("CSL JSON parse failed: %s", exc)
        return []
    if not isinstance(records, list):
        records = [records]
    entries: list[dict[str, Any]] = []
    for r in records:
        out: dict[str, Any] = {}
        if r.get("title"):
            out["title"] = r["title"]
        authors = r.get("author") or []
        if authors:
            names = []
            for a in authors:
                family = a.get("family", "")
                given = a.get("given", "")
                if family and given:
                    names.append(f"{family}, {given}")
                elif family:
                    names.append(family)
            if names:
                out["authors"] = names
        issued = (r.get("issued") or {}).get("date-parts") or [[None]]
        if issued and issued[0][0]:
            out["date"] = str(issued[0][0])
        for k in ("publisher", "DOI", "ISBN", "URL", "language", "volume", "issue"):
            if r.get(k):
                if k == "DOI":
                    out["doi"] = r[k]
                elif k == "ISBN":
                    isbn_clean = re.sub(r"[^0-9X]", "", str(r[k]).upper())
                    if len(isbn_clean) == 13:
                        out["isbn_13"] = isbn_clean
                    elif len(isbn_clean) == 10:
                        out["isbn_10"] = isbn_clean
                elif k == "URL":
                    out["url"] = r[k]
                else:
                    out[k.lower()] = r[k]
        if r.get("container-title"):
            out["journal"] = r["container-title"]
        if r.get("page"):
            out["pages"] = r["page"]
        out["bibtex"] = write_bibtex([out])
        entries.append(out)
    return entries


def read_sidecar(path: str | Path) -> list[dict[str, Any]]:
    """Read a per-file bibliography sidecar next to a source document."""
    p = Path(path)
    candidates = [
        p.with_name(p.stem + ".bib"),
        p.with_name(p.stem + ".ris"),
        p.with_name(p.stem + ".csl.json"),
        p.with_name(p.stem + ".json"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return read_file(candidate)
    return []


def read_folder_sidecars(path: str | Path) -> list[dict[str, Any]]:
    """Read folder-level bibliography sidecars near a source document."""
    p = Path(path)
    folder = p.parent
    candidates = [
        folder / "references.bib",
        folder / "library.bib",
        folder / "zotero-export.json",
        folder / "library.csl.json",
    ]
    for candidate in candidates:
        if candidate.exists():
            return read_file(candidate)
    return []


# =============================================================================
# Exporter — BibTeX from a list of SourceMetadata dicts
# =============================================================================


def _fallback_bibtex_cite_key(entry: dict[str, Any]) -> str:
    authors = entry.get("authors")
    author = authors[0] if isinstance(authors, list) and authors else ""
    surname = str(author).split(",", 1)[0]
    year_match = re.search(r"\d{4}", str(entry.get("year") or entry.get("date") or ""))
    title_word = next(iter(re.findall(r"[A-Za-z0-9]+", str(entry.get("title") or ""))), "")
    key = f"{surname}{year_match.group(0) if year_match else ''}{title_word}".lower()
    return re.sub(r"[^a-z0-9]+", "", key) or "untitled"


def write_bibtex(entries: list[dict[str, Any]]) -> str:
    """Render a list of SourceMetadata dicts as a multi-entry BibTeX file."""
    output_lines: list[str] = []
    for entry in entries:
        if not isinstance(entry, dict):
            logger.warning("write_bibtex: skipping malformed entry: expected dict")
            continue
        bibtex = entry.get("bibtex")
        metadata = entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {}
        if isinstance(bibtex, str) and bibtex.strip():
            output_lines.append(bibtex.strip())
            continue

        title = entry.get("title")
        authors = entry.get("authors")
        if authors is not None and not isinstance(authors, list):
            logger.warning("write_bibtex: skipping malformed entry: authors must be list")
            continue

        entry_type = str(metadata.get("bibtex_entry_type") or "misc")
        cite_key = str(metadata.get("bibtex_cite_key") or _fallback_bibtex_cite_key(entry))
        issue = entry.get("issue")
        if entry.get("kind"):
            entry_type = str(entry["kind"])
        elif entry.get("journal"):
            entry_type = "article"
        elif entry.get("journal_or_book") and entry_type == "misc":
            entry_type = "article"
        elif entry.get("publisher"):
            entry_type = "book"

        fields: list[tuple[str, str]] = []
        if authors:
            fields.append(("author", " and ".join(str(author) for author in authors if author)))
        if title:
            fields.append(("title", str(title)))
        if entry.get("year") is not None:
            fields.append(("year", str(entry["year"])))
        elif entry.get("date"):
            fields.append(("year", str(entry["date"])))

        container = entry.get("journal") or entry.get("journal_or_book")
        if container:
            field_name = "journal" if entry_type == "article" else "booktitle"
            fields.append((field_name, str(container)))
        if entry.get("publisher"):
            fields.append(("publisher", str(entry["publisher"])))
        if entry.get("volume"):
            fields.append(("volume", str(entry["volume"])))
        if issue:
            fields.append(("number", str(issue)))
        if entry.get("pages"):
            fields.append(("pages", str(entry["pages"])))
        if entry.get("doi"):
            fields.append(("doi", str(entry["doi"])))
        if entry.get("isbn_13"):
            fields.append(("isbn", str(entry["isbn_13"])))
        elif entry.get("isbn_10"):
            fields.append(("isbn", str(entry["isbn_10"])))
        elif entry.get("isbn"):
            fields.append(("isbn", str(entry["isbn"])))
        if entry.get("url"):
            fields.append(("url", str(entry["url"])))
        if entry.get("language"):
            fields.append(("language", str(entry["language"])))
        if entry.get("notes"):
            fields.append(("note", str(entry["notes"])))

        emitted = {name for name, _ in fields}
        extra_fields = metadata.get("bibtex_fields")
        if isinstance(extra_fields, dict):
            for name, value in extra_fields.items():
                if name in emitted or value in (None, ""):
                    continue
                fields.append((str(name), str(value)))

        lines = [f"@{entry_type}{{{cite_key},"]
        for name, value in fields:
            lines.append(f"  {name} = {{{value}}},")
        if lines[-1].endswith(","):
            lines[-1] = lines[-1][:-1]
        lines.append("}")
        output_lines.append("\n".join(lines))
    return "\n\n".join(output_lines)


# =============================================================================
# Format detection
# =============================================================================


def detect_format(text: str) -> str:
    """Best-effort detect: 'bibtex' | 'ris' | 'csl_json' | 'unknown'."""
    stripped = text.lstrip()
    if not stripped:
        return "unknown"
    if stripped.startswith(("[", "{")):
        return "csl_json"
    if stripped.startswith("@"):
        return "bibtex"
    if re.search(r"^TY\s+-\s+", stripped, re.MULTILINE):
        return "ris"
    return "unknown"


def read_any(text: str) -> list[dict[str, Any]]:
    """Parse any supported format. Returns empty list when detection fails."""
    fmt = detect_format(text)
    if fmt == "bibtex":
        return read_bibtex(text)
    if fmt == "ris":
        return read_ris(text)
    if fmt == "csl_json":
        return read_csl_json(text)
    return []


def read_file(path: str | Path) -> list[dict[str, Any]]:
    """Read + parse from disk."""
    p = Path(path)
    if not p.exists():
        return []
    return read_any(p.read_text(encoding="utf-8"))
