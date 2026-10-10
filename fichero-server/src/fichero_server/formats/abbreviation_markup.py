"""A line's abbreviation markup, read into its as-written and expanded texts (#5651, `source.reading.abbreviation-markup-parsed`).

Some corpora write their editorial markup INTO a line's text. The Spanish notarial corpus (Transkribus,
`transkribus_spanish-notarial_*.page.xml`) writes:

* ``abbr$.expansion`` -- an abbreviation as written and what it stands for: ``dha$.dicha``;
* ``$^x`` -- letters the scribe wrote raised, inside an abbreviation: ``Parq.$^l$.Parroquial``;
* ``$tag:`` -- a name or a term tagged before the word: ``$ant:Miguel`` (a person), ``$top:Canet`` (a
  place), ``$ofi:`` (an office), ``$tip:`` (a clause type), ``$pag:`` (a page number);
* ``$-`` -- a word broken across lines, at the end of the first line and the start of the next
  (``le:$-`` / ``$-gitima``).

Left in, it reached spaCy raw: one statement's subject read ``$ant``. And a Kraken reader trained on the
lines would learn ``$`` as a letter of the hand.

PAGE XML also says it in the ``custom`` attribute instead of the text:
``abbrev {offset:3; length:3; expansion:dicha;}`` (and ``expan``/``expansion`` spelled either way);
:func:`apply_page_custom` reads that form.

PURE: text in, two texts out. :func:`as_written` is the line as the scribe wrote it, the markup gone and
every abbreviation kept as written; :func:`expanded` is the same line with each abbreviation opened.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: ``$ant:`` and its kin: a tag written before a word. Lower-case letters only, so a ``$`` that is not
#: markup's is never mistaken for one.
_TAG = re.compile(r"\$[a-z]+:")
#: An abbreviation and its expansion: the abbreviation (with any raised letters) up to ``$.``, then the
#: expansion up to the next space, ``$`` or clause punctuation.
_ABBREVIATION = re.compile(r"(?P<abbr>[^\s$]*(?:\$\^[^\s$]+)*)\$\.(?P<expansion>[^\s$,;]+)")
#: Raised letters left over (``$^`` with no expansion after them).
_RAISED = re.compile(r"\$\^")
#: A word broken across lines; in the expanded text the scribe's own break mark before it goes too.
_BREAK = re.compile(r"\$-")
_BREAK_WITH_MARK = re.compile(r"[:=¬-]?\$-")


@dataclass(frozen=True)
class MarkedLine:
    """One line read: as the scribe wrote it, and with its abbreviations opened."""

    as_written: str
    expanded: str


def has_markup(text: str) -> bool:
    """True when the text carries any of the markup this module reads."""
    return bool(_TAG.search(text) or "$." in text or "$^" in text or "$-" in text)


def _strip_leftovers(text: str, marked: bool) -> str:
    # In a marked text, any `$` the patterns above did not account for is markup the corpus did not
    # document; it is never a letter of the line, so it never reaches a reader of the text. A text with
    # no markup keeps its `$` (a price in a ledger is not markup).
    return text.replace("$", "") if marked else text


def as_written(text: str, *, marked: bool | None = None) -> str:
    """The line as written: markup removed, each abbreviation kept as the scribe wrote it.

    ``marked`` says the text comes from a marked corpus (a whole page that has markup); unset, the line
    is asked itself."""
    if marked is None:
        marked = has_markup(text)
    if not marked:
        return text
    out = _TAG.sub("", text)
    out = _ABBREVIATION.sub(lambda match: match.group("abbr"), out)
    out = _RAISED.sub("", out)
    out = _BREAK.sub("", out)
    return _strip_leftovers(out, marked)


def expanded(text: str, *, marked: bool | None = None) -> str:
    """The line with its abbreviations opened: ``dha$.dicha`` is ``dicha``. ``marked`` as for
    :func:`as_written`."""
    if marked is None:
        marked = has_markup(text)
    if not marked:
        return text
    out = _TAG.sub("", text)
    out = _ABBREVIATION.sub(lambda match: match.group("expansion"), out)
    out = _RAISED.sub("", out)
    out = _BREAK_WITH_MARK.sub("", out)
    return _strip_leftovers(out, marked)


def read_line(text: str) -> MarkedLine:
    """Both texts of one line."""
    return MarkedLine(as_written=as_written(text), expanded=expanded(text))


def expanded_text(text: str) -> str:
    """A whole text (lines joined by newlines) with each line's abbreviations opened. A text with no
    markup anywhere is returned exactly as it is."""
    if not has_markup(text):
        return text
    return "\n".join(expanded(line, marked=True) for line in text.split("\n"))


_CUSTOM_ABBREV = re.compile(r"\b(?:abbrev|expan|expansion)\s*\{(?P<body>[^}]*)\}")


def _custom_fields(body: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for part in body.split(";"):
        key, sep, value = part.partition(":")
        if sep:
            fields[key.strip()] = value.strip()
    return fields


def apply_page_custom(text: str, custom: str | None) -> MarkedLine:
    """A PAGE line whose abbreviations are in its ``custom`` attribute, not its text.

    ``abbrev {offset:3; length:3; expansion:dicha;}`` marks ``text[3:6]`` as an abbreviation of
    ``dicha``. The text itself is already as written; the expanded text replaces each marked stretch,
    right to left so earlier offsets stay true. A tag whose stretch falls outside the text, or that names
    no expansion, is left alone. Any inline markup in the text is read as well.
    """
    marks: list[tuple[int, int, str]] = []
    for match in _CUSTOM_ABBREV.finditer(custom or ""):
        fields = _custom_fields(match.group("body"))
        try:
            offset, length = int(fields.get("offset", "")), int(fields.get("length", ""))
        except ValueError:
            continue
        expansion = fields.get("expansion")
        if expansion and 0 <= offset and offset + length <= len(text):
            marks.append((offset, length, expansion.replace("\\u0020", " ")))
    opened = text
    for offset, length, expansion in sorted(marks, reverse=True):
        opened = opened[:offset] + expansion + opened[offset + length :]
    return MarkedLine(as_written=as_written(text), expanded=expanded(opened))
