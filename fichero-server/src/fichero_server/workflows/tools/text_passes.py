"""Programmatic text passes: whitespace, dehyphenation, paragraph un-wrapping,
and cross-page chrome removal.

These are the *mechanical* cleanups a book-like page needs — the ones that need
no model at all. They live beside :mod:`text_cleaning` (whose ``TextCleaner``
composes them) so each pass stays a pure, separately-testable string transform.

The design rule throughout: **never destroy structure the page actually has.**
Tallies, verse, lists and headings are detected and left alone; only genuinely
hard-wrapped prose is rejoined. Every pass is idempotent — running it on its own
output is a no-op — which is what makes the composition safe to re-run.
"""

from __future__ import annotations

import re
import statistics
import unicodedata

from pydantic import BaseModel, Field


class TextPassError(ValueError):
    """Raised when a reflow pass is given input it cannot process."""


class TextCleanOptions(BaseModel):
    """User-facing switches for the deterministic cleaner.

    Deliberately few: one switch per *outcome a reader would notice*, not one
    per internal pass (dead-simple UX, no needless toggles).
    """

    model_config = {"extra": "forbid"}

    fix_ocr: bool = Field(
        default=True,
        description="Apply the narrow OCR token corrections",
    )
    normalize_whitespace: bool = Field(
        default=True,
        description="Trim trailing spaces, expand tabs, drop invisible characters",
    )
    fix_hyphenation: bool = Field(
        default=True,
        description="Rejoin words broken by an end-of-line hyphen",
    )
    reflow_paragraphs: bool = Field(
        default=True,
        description="Join hard-wrapped lines back into paragraphs",
    )
    strip_page_chrome: bool = Field(
        default=True,
        description="Drop running headers/footers and page numbers across pages",
    )
    wrap_width: int | None = Field(
        default=None,
        ge=20,
        description="Hard-wrap the result at this column; None leaves paragraphs whole",
    )


# ===========================================================================
# 1. Whitespace normalization
# ===========================================================================

#: Characters that carry no visible content but break every downstream
#: heuristic (zero-width space/joiner, BOM, soft hyphen handled separately).
_INVISIBLE = dict.fromkeys(
    ord(c) for c in "​‌‍⁠﻿"
)

#: Space-like characters that should read as an ordinary space, including the
#: no-break space that PDF extractors emit between every word of some fonts.
_SPACE_LIKE = re.compile(r"[   -   　\t\v]")


def normalize_whitespace(text: str, preserve_indent: bool = True) -> str:
    """Normalize invisible and space-like characters, runs, and blank lines.

    ``preserve_indent`` keeps a line's leading spaces, because indentation is a
    paragraph-start signal the reflow pass reads. Interior runs always collapse
    to a single space, trailing space always goes, and more than one blank line
    in a row becomes exactly one.
    """
    text = unicodedata.normalize("NFC", text)
    text = text.translate(_INVISIBLE)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _SPACE_LIKE.sub(" ", text)

    out: list[str] = []
    for line in text.split("\n"):
        indent = len(line) - len(line.lstrip(" ")) if preserve_indent else 0
        body = re.sub(r" {2,}", " ", line.strip())
        out.append((" " * indent + body) if body else "")

    # Collapse runs of blank lines to a single blank line.
    collapsed: list[str] = []
    for line in out:
        if not line and collapsed and not collapsed[-1]:
            continue
        collapsed.append(line)
    return "\n".join(collapsed).strip("\n")


# ===========================================================================
# 2. Dehyphenation
# ===========================================================================

_WORD_RE = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)*", flags=re.UNICODE)
#: A line broken mid-word: letters, then a hyphen (or soft hyphen), then EOL.
_TRAILING_HYPHEN = re.compile(r"([^\W\d_]{2,})[-­]$", flags=re.UNICODE)


#: A hyphenated compound written *inside* a line (never at a line end, which
#: is the wrap case this pass exists to undo).
_INLINE_COMPOUND = re.compile(
    r"([^\W\d_]{2,})-([^\W\d_]{2,})(?=[^\n]*\S)", flags=re.UNICODE
)


def _vocabulary(text: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for match in _WORD_RE.finditer(text):
        key = match.group(0).lower()
        counts[key] = counts.get(key, 0) + 1
    return counts


def _inline_compounds(text: str) -> set[str]:
    return {
        f"{m.group(1).lower()}-{m.group(2).lower()}"
        for m in _INLINE_COMPOUND.finditer(text)
    }


def dehyphenate(text: str) -> str:
    """Rejoin words split by an end-of-line hyphen, keeping true compounds.

    The decision is made from the document itself rather than a dictionary, so
    it works identically for Spanish and English (and is accent-safe: the word
    regex is unicode letter based, so ``compañí-\\na`` rejoins correctly):

    * the joined form occurs elsewhere in the document → join, drop the hyphen;
    * the hyphenated form occurs elsewhere → keep the hyphen;
    * both halves stand alone as words elsewhere → keep the hyphen (compound);
    * otherwise → join, because an end-of-line hyphen is overwhelmingly a
      typesetting wrap rather than a real one.
    """
    vocab = _vocabulary(text)
    compounds = _inline_compounds(text)
    lines = text.split("\n")
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        match = _TRAILING_HYPHEN.search(line.rstrip())
        nxt = lines[i + 1] if i + 1 < len(lines) else ""
        if match is None or not nxt.strip():
            out.append(line)
            i += 1
            continue

        head = match.group(1)
        tail_match = _WORD_RE.match(nxt.lstrip())
        # Only a lowercase continuation is a wrap; "Juan-\nPerez" is a name.
        if tail_match is None or not tail_match.group(0)[:1].islower():
            out.append(line)
            i += 1
            continue

        tail = tail_match.group(0)
        joined = f"{head}{tail}".lower()
        hyphenated = f"{head}-{tail}".lower()

        # Both halves are already counted once by this very break, so a count
        # of two is the first evidence the half stands alone in the document.
        if vocab.get(joined, 0) >= 1:
            keep_hyphen = False
        elif hyphenated in compounds:
            keep_hyphen = True
        elif vocab.get(head.lower(), 0) >= 2 and vocab.get(tail.lower(), 0) >= 2:
            keep_hyphen = True
        else:
            keep_hyphen = False

        # Fold the broken word forward onto the next line, keeping this line's
        # indentation so the reflow pass still sees the paragraph shape.
        stem = line.rstrip()[: match.start(1)] + head + ("-" if keep_hyphen else "")
        lines[i + 1] = stem + nxt.lstrip()
        i += 1

    return "\n".join(out)


# ===========================================================================
# 3. Block classification + paragraph reflow
# ===========================================================================

#: Sentence/clause terminators that legitimately end a paragraph, including the
#: Spanish closing quotes and guillemets.
_TERMINALS = ('.', '!', '?', ':', ';', '"', "'", '”', '»', '’', ')', ']')
_LIST_PREFIX = re.compile(
    r"^\s*(?:[-*•·—–]|\(?\d{1,3}[.)]|\(?[a-zA-Z][.)]|[ivxlIVXL]{1,5}[.)])\s+"
)
_NUMERICISH = re.compile(r"[\d\s.,;:+\-–—$£%/()'\"]{1,24}")
_PROSE_MIN_LETTER_RATIO = 0.5


def _is_numeric_line(line: str) -> bool:
    stripped = line.strip()
    return (
        bool(stripped)
        and _NUMERICISH.fullmatch(stripped) is not None
        and any(c.isdigit() for c in stripped)
    )


def _is_prose_line(line: str) -> bool:
    """A line with enough alphabetic signal to belong in a paragraph.

    Garbage lines are left on their own line so the OCR-garbage pass can still
    see and drop them — reflow must never smuggle soup into a good paragraph.
    """
    stripped = line.strip()
    if not stripped:
        return False
    non_space = sum(1 for c in stripped if not c.isspace())
    letters = sum(1 for c in stripped if c.isalpha())
    return non_space > 0 and (letters / non_space) >= _PROSE_MIN_LETTER_RATIO


def _indent_of(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def is_table_block(lines: list[str]) -> bool:
    """A tally/accounts block: several number-shaped lines, a good share of them."""
    body = [ln for ln in lines if ln.strip()]
    if len(body) < 3:
        return False
    numeric = sum(1 for ln in body if _is_numeric_line(ln))
    if numeric >= 3 and numeric / len(body) >= 0.3:
        return True
    # Column-aligned rows (runs of 2+ spaces used as column separators).
    columnar = sum(1 for ln in body if re.search(r"\S {2,}\S", ln))
    return columnar >= 3 and columnar / len(body) >= 0.6


def is_list_block(lines: list[str]) -> bool:
    body = [ln for ln in lines if ln.strip()]
    if not body:
        return False
    marked = sum(1 for ln in body if _LIST_PREFIX.match(ln))
    return marked >= 2 and marked / len(body) >= 0.5


#: No typesetter wraps prose this narrow, so a block whose longest line stays
#: under this width was broken on purpose — verse, an address, a caption.
_VERSE_MAX_WIDTH = 45


def is_verse_block(lines: list[str]) -> bool:
    """Poetry and other deliberately broken short lines.

    The discriminator against hard-wrapped prose is the block's *widest* line:
    wrapped prose runs out to a wrap column (typically 60-80 characters), so a
    block that never reaches 45 was never wrapped — its line breaks are the
    author's. A supporting signal is required as well: the lines mostly do not
    end a sentence, or they mostly begin with a capital.
    """
    body = [ln.strip() for ln in lines if ln.strip()]
    if len(body) < 3:
        return False
    if max(len(ln) for ln in body) > _VERSE_MAX_WIDTH:
        return False
    unterminated = sum(1 for ln in body if not ln.endswith(_TERMINALS))
    capitalized = sum(1 for ln in body if ln[:1].isupper())
    return (
        unterminated / len(body) >= 0.5 or capitalized / len(body) >= 0.6
    )


def is_heading_block(lines: list[str]) -> bool:
    body = [ln.strip() for ln in lines if ln.strip()]
    if len(body) != 1:
        return False
    only = body[0]
    if len(only) > 70 or only.endswith(('.', '!', '?')):
        return False
    return only.isupper() or _indent_of(lines[0]) >= 4 or len(only.split()) <= 8


def _reflow_prose_block(lines: list[str]) -> list[str]:
    """Join hard-wrapped lines of one prose block into paragraphs."""
    body = [ln for ln in lines if ln.strip()]
    if len(body) < 2:
        return [ln.strip() for ln in body]

    lengths = [len(ln.strip()) for ln in body]
    median = statistics.median(lengths)
    base_indent = min(_indent_of(ln) for ln in body)

    paragraphs: list[list[str]] = [[]]
    for idx, line in enumerate(body):
        stripped = line.strip()
        if paragraphs[-1] and _starts_new_paragraph(
            previous=body[idx - 1].strip(),
            current=line,
            median=median,
            base_indent=base_indent,
        ):
            paragraphs.append([])
        paragraphs[-1].append(stripped)

    out: list[str] = []
    for paragraph in paragraphs:
        if not paragraph:
            continue
        if out:
            out.append("")
        out.append(_join_wrapped(paragraph))
    return out


def _starts_new_paragraph(
    previous: str, current: str, median: float, base_indent: int
) -> bool:
    stripped = current.strip()
    # An indented line is a paragraph opener (the classic book signal).
    if _indent_of(current) > base_indent:
        return True
    if _LIST_PREFIX.match(stripped):
        return True
    # Soup never merges into prose, and prose never merges into soup.
    if not _is_prose_line(current) or not _is_prose_line(previous):
        return True
    # A short line that ends a sentence is the end of a paragraph.
    if previous.endswith(_TERMINALS) and len(previous) < median * 0.9:
        return True
    # A markedly short line that is not sentence-final is a heading or a break.
    if len(previous) < median * 0.55:
        return True
    return False


def _join_wrapped(lines: list[str]) -> str:
    joined = lines[0]
    for line in lines[1:]:
        joined = f"{joined} {line}" if joined else line
    return joined


def split_blocks(text: str) -> list[list[str]]:
    """Split into blocks on blank lines, keeping each block's raw indentation."""
    blocks: list[list[str]] = []
    current: list[str] = []
    for line in text.split("\n"):
        if line.strip():
            current.append(line)
        elif current:
            blocks.append(current)
            current = []
    if current:
        blocks.append(current)
    return blocks


def reflow_paragraphs(text: str) -> str:
    """Un-word-wrap prose while leaving tables, verse, lists and headings alone."""
    if not text.strip():
        return ""
    rendered: list[str] = []
    for block in split_blocks(text):
        if (
            is_table_block(block)
            or is_list_block(block)
            or is_verse_block(block)
            or is_heading_block(block)
        ):
            rendered.append("\n".join(ln.strip() for ln in block))
        else:
            rendered.append("\n".join(_reflow_prose_block(block)))
    return "\n\n".join(part for part in rendered if part)


# ===========================================================================
# 4. Cross-page chrome removal
# ===========================================================================

#: A page break as emitted by PDF text extractors, or as written by hand.
_PAGE_SEPARATOR = re.compile(r"\n?\f\n?|\n-{2,}\s*(?:page|página)[^\n]*\n", re.I)
_PAGE_NUMBER = re.compile(
    r"^[\[\(]?\s*(?:\d{1,4}|[ivxlcdm]{1,7}|[IVXLCDM]{1,7})\s*[\]\)]?[.,]?$"
)
#: How many pages a line must repeat on before it counts as running chrome.
_CHROME_MIN_PAGES = 3
#: How many lines at each edge of a page can be chrome.
_EDGE_DEPTH = 2


def split_pages(text: str) -> list[str]:
    """Split a multi-page blob on form feeds or ``--- Page N ---`` markers."""
    return _PAGE_SEPARATOR.split(text)


def _page_is_tabular(lines: list[str]) -> bool:
    """A page whose numbers ARE its content, so edge numbers must be kept.

    Deliberately looser than :func:`is_table_block`: a tally page can be only
    a handful of lines long, and the cost of a false negative here is deleting
    real data.
    """
    body = [ln for ln in lines if ln.strip()]
    if len(body) < 2:
        return False
    numeric = sum(1 for ln in body if _is_numeric_line(ln))
    return numeric >= 2 and numeric / len(body) >= 0.4


def _chrome_key(line: str) -> str:
    """A position-tolerant signature: digits blurred, case and spacing folded."""
    return re.sub(r"\s+", " ", re.sub(r"\d+", "#", line.strip().lower()))


def strip_page_chrome(pages: list[str]) -> list[str]:
    """Drop running headers/footers and page numbers from a multi-page document.

    A line is chrome when the same signature (digits blurred, so ``page 12`` and
    ``page 13`` are the same header) appears in the same edge slot — top or
    bottom — on at least three pages. Bare numbers and roman numerals at an edge
    are page numbers under the same repetition test, so a tally page whose data
    happens to end in a number keeps it.
    """
    if not isinstance(pages, list):
        raise TextPassError("strip_page_chrome expects a list of page texts")
    if len(pages) < _CHROME_MIN_PAGES:
        return list(pages)

    edges: list[tuple[list[int], list[int]]] = []
    top_counts: dict[str, int] = {}
    bottom_counts: dict[str, int] = {}
    per_page_lines: list[list[str]] = []

    for page in pages:
        lines = page.split("\n")
        filled = [i for i, ln in enumerate(lines) if ln.strip()]
        top = filled[:_EDGE_DEPTH]
        bottom = [i for i in filled[-_EDGE_DEPTH:] if i not in top]
        per_page_lines.append(lines)
        edges.append((top, bottom))
        for i in top:
            key = _chrome_key(lines[i])
            top_counts[key] = top_counts.get(key, 0) + 1
        for i in bottom:
            key = _chrome_key(lines[i])
            bottom_counts[key] = bottom_counts.get(key, 0) + 1

    # A page number never repeats its *value*, so the signature test cannot see
    # it. What repeats is the SHAPE: a page-number-sized token sitting in the
    # same edge slot page after page. Tabular pages are exempt — on a tally
    # sheet an edge number is data (the 2026-09-03 Marshall regression).
    tabular = [_page_is_tabular(lines) for lines in per_page_lines]
    top_numbers = sum(
        1
        for lines, (top, _), tab in zip(per_page_lines, edges, tabular)
        if not tab and any(looks_like_page_number(lines[i]) for i in top)
    )
    bottom_numbers = sum(
        1
        for lines, (_, bottom), tab in zip(per_page_lines, edges, tabular)
        if not tab and any(looks_like_page_number(lines[i]) for i in bottom)
    )

    cleaned: list[str] = []
    for lines, (top, bottom), tab in zip(per_page_lines, edges, tabular):
        drop: set[int] = set()
        for i in top:
            if tab and _is_numeric_line(lines[i]):
                continue
            if top_counts.get(_chrome_key(lines[i]), 0) >= _CHROME_MIN_PAGES:
                drop.add(i)
            elif (
                not tab
                and top_numbers >= _CHROME_MIN_PAGES
                and looks_like_page_number(lines[i])
            ):
                drop.add(i)
        for i in bottom:
            if tab and _is_numeric_line(lines[i]):
                continue
            if bottom_counts.get(_chrome_key(lines[i]), 0) >= _CHROME_MIN_PAGES:
                drop.add(i)
            elif (
                not tab
                and bottom_numbers >= _CHROME_MIN_PAGES
                and looks_like_page_number(lines[i])
            ):
                drop.add(i)
        kept = [ln for i, ln in enumerate(lines) if i not in drop]
        cleaned.append("\n".join(kept).strip("\n"))
    return cleaned


def strip_page_chrome_text(text: str, separator: str = "\n\n") -> str:
    """Convenience wrapper: split a blob into pages, de-chrome, rejoin."""
    pages = split_pages(text)
    if len(pages) < _CHROME_MIN_PAGES:
        return text
    return separator.join(p for p in strip_page_chrome(pages) if p.strip())


def looks_like_page_number(line: str) -> bool:
    """True when a line is nothing but a page number (arabic or roman)."""
    return bool(_PAGE_NUMBER.match(line.strip()))


# The workflow tool ``text_reflow`` predates this module and carries its own
# line-join heuristics and its own test suite. It is deliberately left alone
# here; converging the two surfaces onto these passes is a separate change.
