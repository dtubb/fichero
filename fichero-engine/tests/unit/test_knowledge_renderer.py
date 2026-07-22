"""Coverage for the citation renderer ``fichero.knowledge.renderer`` (#912),
previously untested directly. Pure logic: author-name parsing, the per-style
author-list joiners (with their 'et al.' thresholds), year extraction, BibTeX
key/escape, and the four public renderers (BibTeX / Chicago / APA / MLA).

Assertions pin the docstring examples exactly and the joiner threshold
boundaries, so a refactor can't silently shift a citation format.
"""

from __future__ import annotations

from fichero.knowledge.renderer import (
    _author_apa,
    _bibtex_escape,
    _bibtex_key,
    _given_names,
    _join_apa_authors,
    _join_chicago_authors,
    _join_mla_authors,
    _surname,
    _year_from_date,
    render_apa,
    render_bibtex,
    render_chicago,
    render_mla,
)
from fichero.models.knowledge import SourceMetadata


def _meta(**kwargs) -> SourceMetadata:
    return SourceMetadata(**kwargs)


# ===========================================================================
# Name helpers
# ===========================================================================


def test_surname_forms():
    assert _surname("Tubb, Daniel") == "Tubb"
    assert _surname("Daniel Tubb") == "Tubb"
    assert _surname("Daniel M. Tubb") == "Tubb"
    assert _surname("Plato") == "Plato"


def test_given_names_forms():
    assert _given_names("Tubb, Daniel") == "Daniel"
    assert _given_names("Daniel M. Tubb") == "Daniel M."
    assert _given_names("Plato") == ""  # single token -> no given names


def test_author_apa_initials():
    assert _author_apa("Tubb, Daniel") == "Tubb, D."
    assert _author_apa("Daniel M. Tubb") == "Tubb, D. M."
    assert _author_apa("Plato") == "Plato"  # no given -> surname only


# ===========================================================================
# Author-list joiners — threshold boundaries
# ===========================================================================


def test_chicago_joiner_thresholds():
    assert _join_chicago_authors([]) == ""
    assert _join_chicago_authors(["Tubb, Daniel"]) == "Tubb, Daniel"
    assert _join_chicago_authors(["Tubb, Daniel", "Smith, Bob"]) == "Tubb, Daniel, and Bob Smith"
    assert (
        _join_chicago_authors(["Tubb, Daniel", "Smith, Bob", "Roe, Ann"])
        == "Tubb, Daniel, Bob Smith, and Ann Roe"
    )
    # 4+ collapses to et al.
    assert _join_chicago_authors(["Tubb, Daniel", "A B", "C D", "E F"]) == "Tubb, Daniel, et al."


def test_apa_joiner_thresholds():
    assert _join_apa_authors(["Tubb, Daniel"]) == "Tubb, D."
    assert _join_apa_authors(["Tubb, Daniel", "Smith, Bob"]) == "Tubb, D., & Smith, B."
    assert (
        _join_apa_authors(["Tubb, Daniel", "Smith, Bob", "Roe, Ann"])
        == "Tubb, D., Smith, B., & Roe, A."
    )
    # 21+ collapses to et al.
    big = [f"Last{i}, First{i}" for i in range(21)]
    assert _join_apa_authors(big) == "Last0, F. et al."


def test_mla_joiner_thresholds():
    assert _join_mla_authors(["Tubb, Daniel"]) == "Tubb, Daniel"
    assert _join_mla_authors(["Tubb, Daniel", "Smith, Bob"]) == "Tubb, Daniel, and Bob Smith"
    # 3+ collapses to et al.
    assert (
        _join_mla_authors(["Tubb, Daniel", "Smith, Bob", "Roe, Ann"]) == "Tubb, Daniel, et al."
    )


# ===========================================================================
# _year_from_date / _bibtex_key / _bibtex_escape
# ===========================================================================


def test_year_from_date_formats():
    assert _year_from_date("2020-03-15") == "2020"
    assert _year_from_date("15 de marzo de 2020") == "2020"
    assert _year_from_date("2020") == "2020"
    # word-bounded so a decade like '1200s' is skipped in favour of the real year
    assert _year_from_date("circa 1200s, published 2020") == "2020"
    assert _year_from_date("no year here") is None
    assert _year_from_date(None) is None
    assert _year_from_date("") is None


def test_bibtex_key_generation():
    assert _bibtex_key(_meta(authors=["Tubb, Daniel"], title="Shifting Livelihoods", date="2020")) == "tubb2020shifting"
    # No author -> anon; no date -> nd.
    assert _bibtex_key(_meta(title="Alone", date=None)).startswith("anon")
    assert "nd" in _bibtex_key(_meta(authors=["Roe, Ann"], title="Untitled Work", date=None))
    # Accented surname is ASCII-stripped.
    assert _bibtex_key(_meta(authors=["Nariño, José"], title="Río", date="1999")) == "nario1999ro"


def test_bibtex_escape_special_chars():
    assert _bibtex_escape("A & B") == r"A \& B"
    assert _bibtex_escape("50% off") == r"50\% off"
    assert _bibtex_escape("a_b {c}") == r"a\_b \{c\}"
    # Backslash escaped first so added escapes aren't double-escaped.
    assert _bibtex_escape("x\\y") == r"x\\y"


# ===========================================================================
# render_bibtex
# ===========================================================================


def test_render_bibtex_book_matches_docstring():
    m = _meta(authors=["Roe, Avery"], title="Example Research", date="2020", publisher="Example Press")
    assert render_bibtex(m) == (
        "@book{roe2020example,\n"
        "  author = {Roe, Avery},\n"
        "  title = {Example Research},\n"
        "  year = {2020},\n"
        "  publisher = {Example Press}\n"
        "}"
    )


def test_render_bibtex_article_type_from_journal():
    m = _meta(authors=["Roe, Ann"], title="A Study", date="2019", journal="J. Testing", volume="12", issue="3", pages="45-67")
    out = render_bibtex(m)
    assert out.startswith("@article{")
    assert "journal = {J. Testing}" in out
    assert "number = {3}" in out  # issue maps to 'number'
    assert "pages = {45-67}" in out


def test_render_bibtex_archive_is_misc_even_with_publisher():
    m = _meta(title="Record", archive_name="AGN", publisher="Somebody")
    assert render_bibtex(m).startswith("@misc{")


def test_render_bibtex_passthrough_when_bibtex_present():
    m = _meta(title="X", bibtex="@book{precomputed, title={X}}\n")
    assert render_bibtex(m) == "@book{precomputed, title={X}}"


def test_render_bibtex_isbn_preference():
    assert "isbn = {9783161484100}" in render_bibtex(_meta(title="T", isbn_13="9783161484100", isbn_10="0306406152"))
    assert "isbn = {0306406152}" in render_bibtex(_meta(title="T", isbn_10="0306406152"))


def test_render_bibtex_escapes_field_values():
    out = render_bibtex(_meta(title="Cats & Dogs", date="2000"))
    assert r"Cats \& Dogs" in out


def test_render_bibtex_cite_key_override():
    m = _meta(authors=["Tubb, Daniel"], title="X", date="2020", publisher="Duke")
    assert render_bibtex(m, cite_key="doc-123").startswith("@book{doc-123,")


# ===========================================================================
# render_chicago / apa / mla — docstring examples + article form
# ===========================================================================


def test_render_chicago_matches_docstring():
    m = _meta(authors=["Roe, Avery"], title="Example Research", date="2020", publisher="Example Press")
    assert render_chicago(m) == "Roe, Avery. 2020. *Example Research*. Example Press."


def test_render_chicago_article_form():
    m = _meta(authors=["Roe, Ann"], title="A Study", date="2019", journal="J. Testing", volume="12", issue="3", pages="45-67")
    out = render_chicago(m)
    assert '"A Study."' in out
    assert "*J. Testing*" in out
    assert "12, no. 3:" in out
    assert "45-67." in out


def test_render_apa_matches_docstring():
    m = _meta(authors=["Roe, Avery"], title="Example Research", date="2020", publisher="Example Press")
    assert render_apa(m) == "Roe, A. (2020). *Example Research*. Example Press."


def test_render_apa_no_date_is_nd():
    out = render_apa(_meta(authors=["Tubb, Daniel"], title="X", date=None))
    assert "(n.d.)." in out


def test_render_apa_doi_appended():
    out = render_apa(_meta(authors=["Roe, Ann"], title="X", date="2020", doi="10.1234/x"))
    assert out.endswith("https://doi.org/10.1234/x")


def test_render_mla_matches_docstring():
    m = _meta(authors=["Roe, Avery"], title="Example Research", date="2020", publisher="Example Press")
    assert render_mla(m) == "Roe, Avery. *Example Research*. Example Press, 2020."


def test_render_mla_article_form():
    m = _meta(authors=["Roe, Ann"], title="A Study", date="2019", journal="J. Testing", volume="12", issue="3", pages="45-67")
    out = render_mla(m)
    assert '"A Study."' in out
    assert "*J. Testing*" in out
    assert "vol. 12" in out
    assert "no. 3" in out
    assert "pp. 45-67" in out


def test_renderers_handle_empty_metadata_without_crashing():
    empty = _meta()
    # No author, title, etc. — must produce a string, never raise.
    assert isinstance(render_chicago(empty), str)
    assert isinstance(render_apa(empty), str)
    assert isinstance(render_mla(empty), str)
    assert render_bibtex(empty).startswith("@")
