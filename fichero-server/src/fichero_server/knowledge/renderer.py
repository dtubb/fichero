"""Citation renderers — BibTeX / Chicago / APA / MLA (#912).

Takes a ``SourceMetadata`` row and returns a formatted citation
string in one of the four canonical academic styles. Hand-rolled
rather than depending on citeproc-py: the four styles cover ~95%
of fichero's use case, and the hand-roll keeps fichero free of a
heavy CSL processor dependency for the common path.

If a user wants a less-common style (Vancouver, Harvard, IEEE,
etc.), they can install citeproc-py separately and pass a CSL
file path via the ``render_csl(metadata, style_xml)`` future API.
For now we ship the four prize formats.

Examples — for ``SourceMetadata(authors=["Roe, Avery"],
title="Example Research", date="2020", publisher="Example
Press")``:

  render_bibtex:
    @book{roe2020example,
      author = {Roe, Avery},
      title = {Example Research},
      year = {2020},
      publisher = {Example Press},
    }

  render_chicago:
    Roe, Avery. 2020. *Example Research*. Example Press.

  render_apa:
    Roe, A. (2020). *Example Research*. Example Press.

  render_mla:
    Roe, Avery. *Example Research*. Example Press, 2020.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from fichero_server.models.knowledge import SourceMetadata


# =============================================================================
# Helpers
# =============================================================================


def _year_from_date(date_str: str | None) -> str | None:
    """Pull the 4-digit year out of any common date format.

    Handles ISO-8601 (``2020-03-15``), bare year (``2020``), Spanish
    long-form (``15 de marzo de 2020``), etc. Falls back to None when
    no year is detectable.
    """
    if not date_str:
        return None
    match = re.search(r"\b(\d{4})\b", date_str)
    return match.group(1) if match else None


def _surname(author: str) -> str:
    """Best-effort extraction of an author's surname.

    Accepts "Last, First" or "First Last" or "First M. Last". The
    surname is the part before the first comma, or the last token
    when no comma is present.
    """
    author = author.strip()
    if "," in author:
        return author.split(",", 1)[0].strip()
    parts = author.split()
    return parts[-1] if parts else author


def _initial(name: str) -> str:
    """First letter of a given name, with a period."""
    name = name.strip()
    if not name:
        return ""
    return f"{name[0]}."


def _given_names(author: str) -> str:
    """Given names in 'First Middle' order, regardless of input form."""
    author = author.strip()
    if "," in author:
        last, given = author.split(",", 1)
        return given.strip()
    parts = author.split()
    return " ".join(parts[:-1]) if len(parts) > 1 else ""


def _author_apa(author: str) -> str:
    """APA-style: 'Last, F. M.'"""
    last = _surname(author)
    given = _given_names(author)
    if not given:
        return last
    initials = " ".join(_initial(g) for g in given.split())
    return f"{last}, {initials}"


def _author_chicago_first(author: str) -> str:
    """Chicago author-date first-author form: 'Last, First Middle'."""
    last = _surname(author)
    given = _given_names(author)
    return f"{last}, {given}".strip(", ")


def _author_chicago_subsequent(author: str) -> str:
    """Chicago subsequent-author form: 'First Middle Last'."""
    last = _surname(author)
    given = _given_names(author)
    return f"{given} {last}".strip()


def _join_chicago_authors(authors: list[str]) -> str:
    """Chicago / Turabian author list joiner.

    1 author: ``Last, First``
    2: ``Last, First, and First Last``
    3: ``Last, First, First Last, and First Last``
    4+: ``Last, First, et al.``
    """
    if not authors:
        return ""
    if len(authors) == 1:
        return _author_chicago_first(authors[0])
    if len(authors) >= 4:
        return f"{_author_chicago_first(authors[0])}, et al."

    formatted = [_author_chicago_first(authors[0])]
    for author in authors[1:-1]:
        formatted.append(_author_chicago_subsequent(author))
    formatted.append(f"and {_author_chicago_subsequent(authors[-1])}")
    return ", ".join(formatted)


def _join_apa_authors(authors: list[str]) -> str:
    """APA 7 author list joiner. ``& `` before final; 'et al.' at 21+."""
    if not authors:
        return ""
    formatted = [_author_apa(a) for a in authors]
    if len(formatted) == 1:
        return formatted[0]
    if len(formatted) >= 21:
        return f"{formatted[0]} et al."
    return ", ".join(formatted[:-1]) + f", & {formatted[-1]}"


def _join_mla_authors(authors: list[str]) -> str:
    """MLA 9 author list joiner."""
    if not authors:
        return ""
    if len(authors) == 1:
        return _author_chicago_first(authors[0])
    if len(authors) >= 3:
        return f"{_author_chicago_first(authors[0])}, et al."
    # 2 authors: "Last, First, and First Last."
    second = _author_chicago_subsequent(authors[1])
    return f"{_author_chicago_first(authors[0])}, and {second}"


def _bibtex_key(metadata: "SourceMetadata") -> str:
    """Generate a stable BibTeX cite key.

    Pattern: ``<firstAuthorSurnameLower><year><firstTitleWordLower>``,
    e.g. ``tubb2020shifting``. ASCII-stripped so it's safe for any
    BibTeX engine.
    """
    last = _surname(metadata.authors[0]) if metadata.authors else "anon"
    last_norm = re.sub(r"[^a-z]", "", last.lower())
    year = _year_from_date(metadata.date) or "nd"
    title = metadata.title or "untitled"
    first_word = re.sub(r"[^a-z]", "", title.split()[0].lower()) if title.split() else "x"
    return f"{last_norm}{year}{first_word}"


def _entry_type(metadata: "SourceMetadata") -> str:
    """BibTeX entry type from the metadata shape."""
    if metadata.journal:
        return "article"
    if metadata.archive_name or metadata.archive_identifier:
        return "misc"  # archive records — no perfect BibTeX type
    if metadata.publisher:
        return "book"
    return "misc"


def _bibtex_escape(text: str) -> str:
    """Escape characters that are special in BibTeX values."""
    return (
        text.replace("\\", r"\\")
            .replace("&", r"\&")
            .replace("%", r"\%")
            .replace("$", r"\$")
            .replace("#", r"\#")
            .replace("_", r"\_")
            .replace("{", r"\{")
            .replace("}", r"\}")
    )


# =============================================================================
# Public renderers
# =============================================================================


def render_bibtex(metadata: "SourceMetadata", cite_key: str | None = None) -> str:
    """BibTeX entry.

    ``cite_key`` overrides the auto-generated key when the caller has
    a stable id of its own (e.g. document_id).
    """
    if metadata.bibtex:
        return metadata.bibtex.strip()

    key = cite_key or _bibtex_key(metadata)
    entry_type = _entry_type(metadata)

    fields: list[tuple[str, str]] = []
    if metadata.authors:
        fields.append(("author", " and ".join(metadata.authors)))
    if metadata.title:
        fields.append(("title", metadata.title))
    year = _year_from_date(metadata.date)
    if year:
        fields.append(("year", year))
    if metadata.publisher:
        fields.append(("publisher", metadata.publisher))
    if metadata.journal:
        fields.append(("journal", metadata.journal))
    if metadata.volume:
        fields.append(("volume", metadata.volume))
    if metadata.issue:
        fields.append(("number", metadata.issue))
    if metadata.pages:
        fields.append(("pages", metadata.pages))
    if metadata.doi:
        fields.append(("doi", metadata.doi))
    if metadata.isbn_13:
        fields.append(("isbn", metadata.isbn_13))
    elif metadata.isbn_10:
        fields.append(("isbn", metadata.isbn_10))
    if metadata.url:
        fields.append(("url", metadata.url))
    if metadata.language:
        fields.append(("language", metadata.language))

    lines = [f"@{entry_type}{{{key},"]
    for name, value in fields:
        lines.append(f"  {name} = {{{_bibtex_escape(value)}}},")
    # Remove trailing comma on the last field for a cleaner output.
    if lines[-1].endswith(","):
        lines[-1] = lines[-1][:-1]
    lines.append("}")
    return "\n".join(lines)


def render_chicago(metadata: "SourceMetadata") -> str:
    """Chicago author-date citation. (No bibliography vs notes split;
    we render the bibliography form, which is what users paste into
    their reference list.)
    """
    parts: list[str] = []
    authors = _join_chicago_authors(metadata.authors)
    if authors:
        parts.append(f"{authors}.")
    year = _year_from_date(metadata.date)
    if year:
        parts.append(f"{year}.")
    if metadata.title:
        # Books / archival items italicised; articles in quotes.
        if metadata.journal:
            parts.append(f'"{metadata.title}."')
            parts.append(f"*{metadata.journal}*")
            if metadata.volume:
                vol_part = metadata.volume
                if metadata.issue:
                    vol_part += f", no. {metadata.issue}"
                parts.append(f"{vol_part}:")
            if metadata.pages:
                parts.append(f"{metadata.pages}.")
        else:
            parts.append(f"*{metadata.title}*.")
            if metadata.publisher:
                parts.append(f"{metadata.publisher}.")
    elif metadata.publisher:
        parts.append(f"{metadata.publisher}.")
    if metadata.doi:
        parts.append(f"https://doi.org/{metadata.doi}.")
    elif metadata.url:
        parts.append(f"{metadata.url}.")
    return " ".join(parts).strip()

def render_apa(metadata: "SourceMetadata") -> str:
    """APA 7 reference. Bibliography form (no in-text)."""
    parts: list[str] = []
    authors = _join_apa_authors(metadata.authors)
    if authors:
        parts.append(f"{authors}")
    year = _year_from_date(metadata.date)
    parts.append(f"({year}).") if year else parts.append("(n.d.).")
    if metadata.title:
        if metadata.journal:
            parts.append(f"{metadata.title}.")
            parts.append(f"*{metadata.journal}*")
            if metadata.volume:
                vol_part = f"*{metadata.volume}*"
                if metadata.issue:
                    vol_part += f"({metadata.issue})"
                parts.append(vol_part + ",")
            if metadata.pages:
                parts.append(f"{metadata.pages}.")
        else:
            parts.append(f"*{metadata.title}*.")
            if metadata.publisher:
                parts.append(f"{metadata.publisher}.")
    elif metadata.publisher:
        parts.append(f"{metadata.publisher}.")
    if metadata.doi:
        parts.append(f"https://doi.org/{metadata.doi}")
    elif metadata.url:
        parts.append(metadata.url)
    out = " ".join(parts).strip()
    return out


def render_mla(metadata: "SourceMetadata") -> str:
    """MLA 9 works-cited entry."""
    parts: list[str] = []
    authors = _join_mla_authors(metadata.authors)
    if authors:
        parts.append(f"{authors}.")
    if metadata.title:
        if metadata.journal:
            parts.append(f'"{metadata.title}."')
            container = f"*{metadata.journal}*"
            if metadata.volume:
                container += f", vol. {metadata.volume}"
            if metadata.issue:
                container += f", no. {metadata.issue}"
            year = _year_from_date(metadata.date)
            if year:
                container += f", {year}"
            if metadata.pages:
                container += f", pp. {metadata.pages}"
            parts.append(container + ".")
        else:
            parts.append(f"*{metadata.title}*.")
            if metadata.publisher:
                year = _year_from_date(metadata.date)
                if year:
                    parts.append(f"{metadata.publisher}, {year}.")
                else:
                    parts.append(f"{metadata.publisher}.")
            else:
                year = _year_from_date(metadata.date)
                if year:
                    parts.append(f"{year}.")
    if metadata.doi:
        parts.append(f"https://doi.org/{metadata.doi}.")
    elif metadata.url:
        parts.append(f"{metadata.url}.")
    return " ".join(parts).strip()


__all__ = [name for name in globals() if not name.startswith("__")]
