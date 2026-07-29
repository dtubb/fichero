"""Bibliography importer tests (#909)."""

from __future__ import annotations

from fichero_server.bibliography.importers import (
    detect_format,
    read_any,
    read_bibtex,
    read_csl_json,
    read_ris,
    write_bibtex,
)


BIBTEX_SAMPLE = """
@book{tubb2020shifting,
  author = {Tubb, Daniel},
  title = {Shifting Livelihoods},
  year = {2020},
  publisher = {Duke University Press}
}

@article{garcia2018mining,
  author = {García, María and López, Juan},
  title = {Mining in the Chocó},
  journal = {Journal of Latin American Studies},
  year = {2018},
  volume = {50},
  number = {3},
  pages = {500-525},
  doi = {10.1017/S0022216X18000123}
}
"""

RIS_SAMPLE = """TY  - BOOK
AU  - Tubb, Daniel
TI  - Shifting Livelihoods
PY  - 2020
PB  - Duke University Press
ER  -

TY  - JOUR
AU  - García, María
AU  - López, Juan
TI  - Mining in the Chocó
JO  - Journal of Latin American Studies
VL  - 50
IS  - 3
SP  - 500
EP  - 525
PY  - 2018
DO  - 10.1017/S0022216X18000123
ER  -
"""

CSL_SAMPLE = """[
  {
    "id": "tubb2020",
    "type": "book",
    "title": "Shifting Livelihoods",
    "author": [{"family": "Tubb", "given": "Daniel"}],
    "issued": {"date-parts": [[2020]]},
    "publisher": "Duke University Press"
  }
]"""


class TestBibTeXReader:
    def test_book_entry(self):
        entries = read_bibtex(BIBTEX_SAMPLE)
        book = next((e for e in entries if e.get("title") == "Shifting Livelihoods"), None)
        assert book is not None
        assert book["authors"] == ["Tubb, Daniel"]
        assert book["date"] == "2020"
        assert book["publisher"] == "Duke University Press"

    def test_article_entry_with_two_authors(self):
        entries = read_bibtex(BIBTEX_SAMPLE)
        art = next((e for e in entries if e.get("journal")), None)
        assert art is not None
        assert art["authors"] == ["García, María", "López, Juan"]
        assert art["volume"] == "50"
        assert art["issue"] == "3"
        assert art["doi"] == "10.1017/S0022216X18000123"


class TestRISReader:
    def test_book_entry(self):
        entries = read_ris(RIS_SAMPLE)
        book = next((e for e in entries if e.get("title") == "Shifting Livelihoods"), None)
        assert book is not None
        assert book["authors"] == ["Tubb, Daniel"]
        assert book["date"] == "2020"
        assert book["publisher"] == "Duke University Press"

    def test_article_with_combined_pages(self):
        entries = read_ris(RIS_SAMPLE)
        art = next((e for e in entries if e.get("journal")), None)
        assert art is not None
        assert "500-525" in art.get("pages", "")
        assert art["authors"] == ["García, María", "López, Juan"]


class TestCSLReader:
    def test_zotero_book(self):
        entries = read_csl_json(CSL_SAMPLE)
        assert len(entries) == 1
        e = entries[0]
        assert e["title"] == "Shifting Livelihoods"
        assert e["authors"] == ["Tubb, Daniel"]
        assert e["date"] == "2020"


class TestFormatDetection:
    def test_detects_bibtex(self):
        assert detect_format(BIBTEX_SAMPLE) == "bibtex"

    def test_detects_ris(self):
        assert detect_format(RIS_SAMPLE) == "ris"

    def test_detects_csl_json(self):
        assert detect_format(CSL_SAMPLE) == "csl_json"

    def test_unknown_returns_unknown(self):
        assert detect_format("random text") == "unknown"


class TestReadAny:
    def test_dispatches_correctly(self):
        assert len(read_any(BIBTEX_SAMPLE)) == 2
        assert len(read_any(RIS_SAMPLE)) == 2
        assert len(read_any(CSL_SAMPLE)) == 1


class TestWriteBibtex:
    def test_roundtrip_through_zotero_csl(self):
        """Import Zotero CSL JSON → export as BibTeX → re-parse.
        Should preserve the title + author + year."""
        entries = read_csl_json(CSL_SAMPLE)
        out = write_bibtex(entries)
        assert "@book{tubb2020shifting" in out
        # Re-parse to confirm the round-trip.
        reparsed = read_bibtex(out)
        assert reparsed[0]["title"] == "Shifting Livelihoods"
