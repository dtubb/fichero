"""Citation renderer tests (#912)."""

from __future__ import annotations

from fichero_server.citations import render_apa, render_bibtex, render_chicago, render_mla
from fichero_server.models.knowledge import SourceMetadata


# A book — a reference book, used throughout the test corpus.
TUBB_BOOK = SourceMetadata(
    authors=["Tubb, Daniel"],
    title="Shifting Livelihoods",
    date="2020",
    publisher="Duke University Press",
)

# A journal article — multiple authors.
JOURNAL = SourceMetadata(
    authors=["García, María", "López, Juan", "Rodríguez, Ana"],
    title="Mining and Marginalization in the Chocó",
    journal="Journal of Latin American Studies",
    volume="52",
    issue="3",
    pages="500-525",
    date="2020-08-15",
    doi="10.1017/S0022216X20000543",
)

# An archive record — minimal metadata.
ARCHIVE = SourceMetadata(
    authors=["Córdoba, Eugenio"],
    title="Petición de Herederos",
    date="23 de julio de 1933",
    archive_name="Archivo General de la Nación",
)


class TestBibtex:
    def test_book_with_single_author(self):
        out = render_bibtex(TUBB_BOOK)
        assert "@book{tubb2020shifting" in out
        assert "author = {Tubb, Daniel}" in out
        assert "title = {Shifting Livelihoods}" in out
        assert "year = {2020}" in out
        assert "publisher = {Duke University Press}" in out

    def test_article_with_journal(self):
        out = render_bibtex(JOURNAL)
        assert "@article{" in out
        assert "journal = {Journal of Latin American Studies}" in out
        assert "doi = {10.1017/S0022216X20000543}" in out

    def test_multiple_authors_join_with_and(self):
        out = render_bibtex(JOURNAL)
        assert "García, María and López, Juan and Rodríguez, Ana" in out

    def test_explicit_cite_key(self):
        out = render_bibtex(TUBB_BOOK, cite_key="my-stable-id")
        assert "@book{my-stable-id," in out

    def test_no_authors_falls_back(self):
        meta = SourceMetadata(title="Anonymous Pamphlet", date="1850")
        out = render_bibtex(meta)
        assert "@misc{anon1850anonymous" in out

    def test_special_chars_escaped(self):
        meta = SourceMetadata(
            authors=["Smith, Bob"],
            title="History & Theory",
            date="1990",
            publisher="Wiley",
        )
        out = render_bibtex(meta)
        assert r"History \& Theory" in out

    def test_prefers_stored_canonical_bibtex(self):
        meta = SourceMetadata(
            authors=["Smith, Bob"],
            title="History & Theory",
            date="1990",
            publisher="Wiley",
            bibtex="@misc{stored,\n  note = {canonical}\n}",
        )
        assert render_bibtex(meta) == "@misc{stored,\n  note = {canonical}\n}"


class TestChicago:
    def test_book_format(self):
        out = render_chicago(TUBB_BOOK)
        assert "Tubb, Daniel" in out
        assert "2020" in out
        assert "*Shifting Livelihoods*" in out
        assert "Duke University Press" in out

    def test_article_with_journal_uses_quotes_and_italics(self):
        out = render_chicago(JOURNAL)
        assert '"Mining and Marginalization in the Chocó."' in out
        assert "*Journal of Latin American Studies*" in out
        assert "52, no. 3" in out
        assert "500-525" in out

    def test_three_authors_uses_full_list(self):
        out = render_chicago(JOURNAL)
        # Chicago: Last, First, First Last, and First Last.
        assert "García, María" in out
        assert "and Ana Rodríguez" in out

    def test_doi_link_appended(self):
        out = render_chicago(JOURNAL)
        assert "https://doi.org/10.1017/S0022216X20000543" in out


class TestApa:
    def test_book_format(self):
        out = render_apa(TUBB_BOOK)
        assert out.startswith("Tubb, D.")
        assert "(2020)" in out
        assert "*Shifting Livelihoods*" in out

    def test_three_authors_use_ampersand_before_last(self):
        out = render_apa(JOURNAL)
        # APA: "García, M., López, J., & Rodríguez, A."
        assert "García, M." in out
        assert "& Rodríguez, A." in out

    def test_journal_format(self):
        out = render_apa(JOURNAL)
        assert "*Journal of Latin American Studies*" in out
        assert "*52*(3)" in out


class TestMla:
    def test_book_format(self):
        out = render_mla(TUBB_BOOK)
        assert out.startswith("Tubb, Daniel.")
        assert "*Shifting Livelihoods*" in out
        assert "Duke University Press, 2020" in out

    def test_journal_format(self):
        out = render_mla(JOURNAL)
        assert '"Mining and Marginalization in the Chocó."' in out
        assert "*Journal of Latin American Studies*" in out
        assert "vol. 52" in out
        assert "no. 3" in out
        assert "pp. 500-525" in out

    def test_three_authors_use_et_al(self):
        out = render_mla(JOURNAL)
        # MLA 9: 3+ authors → et al.
        assert "et al." in out


class TestArchiveRecord:
    """Archive sources are the messy case — they often lack publisher
    or journal but have a date + holding institution."""

    def test_bibtex_falls_back_to_misc(self):
        out = render_bibtex(ARCHIVE)
        assert "@misc{" in out
        # Archive name doesn't have a perfect BibTeX field but year
        # + author + title should still appear.
        assert "Córdoba, Eugenio" in out
        assert "year = {1933}" in out

    def test_chicago_extracts_year_from_long_date(self):
        out = render_chicago(ARCHIVE)
        assert "1933" in out
        assert "Córdoba, Eugenio" in out


class TestYearExtraction:
    def test_iso_date_yields_year(self):
        meta = SourceMetadata(title="X", date="2020-03-15")
        out = render_apa(meta)
        assert "(2020)" in out

    def test_no_date_yields_nd(self):
        meta = SourceMetadata(title="Undated Manuscript")
        out = render_apa(meta)
        assert "(n.d.)" in out

    def test_spanish_long_form_year(self):
        meta = SourceMetadata(title="X", date="23 de julio de 1933")
        out = render_apa(meta)
        assert "(1933)" in out
