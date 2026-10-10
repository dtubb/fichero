"""A corpus's abbreviation markup read into a line's as-written and expanded texts (#5651,
`source.reading.abbreviation-markup-parsed`).

The Spanish notarial corpus writes `dha$.dicha`, `$ant:Miguel`, `Parq.$^l$.Parroquial` and `le:$-` into
its lines. Read raw, spaCy took `$ant` for a subject; a Kraken reader trained on it would learn `$` as a
letter. Asserted on every line of the real corpus page, not on hand-made strings alone.
"""
from __future__ import annotations

from pathlib import Path

from lxml import etree

from fichero_server.formats.abbreviation_markup import (
    apply_page_custom,
    as_written,
    expanded,
    expanded_text,
    read_line,
)

PAGE = Path(__file__).parent / "fixtures" / "corpus" / "transkribus_spanish-notarial_0074.page.xml"


def _fixture_lines() -> list[str]:
    root = etree.parse(str(PAGE)).getroot()
    return [u.text for u in root.iter("{*}Unicode") if u.text]


def test_no_markup_survives_any_line_of_the_corpus_page():
    """WHY: anything left of the markup reaches spaCy (expanded) or a Kraken reader (as written) as if it
    were the scribe's ink. The page has markup on most lines; neither text may keep a `$`."""
    lines = _fixture_lines()
    assert sum("$" in line for line in lines) > 20, "the fixture is the marked corpus page"
    for line in lines:
        read = read_line(line)
        assert "$" not in read.as_written, line
        assert "$" not in read.expanded, line


def test_an_abbreviation_is_kept_as_written_and_opened_when_expanded():
    """WHY: the as-written text is the diplomatic record (`dha`), the expanded one what names and
    statements are read from (`dicha`). Swapping them loses one or the other."""
    line = "Parq.$^l$.Parroquial Igla$.Iglesia de dha$.dicha villa de $top:Canet Padre é, hijo"
    assert as_written(line) == "Parq.l Igla de dha villa de Canet Padre é, hijo"
    assert expanded(line) == "Parroquial Iglesia de dicha villa de Canet Padre é, hijo"


def test_tags_go_and_the_tagged_words_stay():
    """WHY: `$ant:` came out of spaCy as a statement's subject. The tag is markup; the name is ink."""
    line = "y el $ofi:Rndo$.Reverendo $ant:Miguel $ant:Carreras $ofi:pbro$.presbítero residente en la"
    assert expanded(line) == "y el Reverendo Miguel Carreras presbítero residente en la"
    assert as_written(line) == "y el Rndo Miguel Carreras pbro residente en la"


def test_a_word_broken_across_lines_loses_its_marker():
    """WHY: `$-` marks the break, not a letter; the scribe's own break mark (`:`) is ink as written and
    dropped only from the expanded text."""
    assert read_line("drôs$.derechos de le:$-").as_written == "drôs de le:"
    assert read_line("drôs$.derechos de le:$-").expanded == "derechos de le"
    assert read_line("$-gitima Paterna").expanded == "gitima Paterna"


def test_a_text_with_no_markup_is_returned_exactly_as_it_is():
    """WHY: a price in a ledger (`$5`) is ink, and a page with no markup must reach spaCy unchanged."""
    text = "Paid $5 to the cooper.\nAnd 3 to the smith."
    assert expanded_text(text) == text
    assert as_written("Paid $5 to the cooper.") == "Paid $5 to the cooper."


def test_page_custom_abbrev_tags_are_opened():
    """WHY: PAGE files from Transkribus also say it in `custom` (`abbrev {offset; length; expansion}`)
    with the text already as written; the expanded text must open each stretch, right to left."""
    text = "de dha villa del dho Patron"
    custom = ("readingOrder {index:3;} abbrev {offset:3; length:3; expansion:dicha;} "
              "abbrev {offset:17; length:3;expansion:dicho;}")
    read = apply_page_custom(text, custom)
    assert read.as_written == text
    assert read.expanded == "de dicha villa del dicho Patron"
